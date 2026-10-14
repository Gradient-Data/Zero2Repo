# feature: F04
"""Acceptance tests for the always-on writing contract (FP-04)."""

from __future__ import annotations

import json
import os
import time

import pytest

from _harness import ENV_DEFAULT_MODE, LEDGER_PREFIX, ledger_paths, workspace
from F01_helpers import (
    proxy_sink,
    scan_stdin,
)
from F02_helpers import runtime_token
from F04_helpers import (
    BANNED_VOCABULARY,
    CONTEXT_ONLY,
    hook_connect_observer,
    make_flag_unreadable,
    make_flag_unwritable,
    named_score_present,
    ordinary_prompt,
    payload_string_values,
    require_banned_list,
    require_empty_stdout,
    require_exported_contract_omits_machine_identity,
    require_full_scoring,
    require_lite_omits_scoring,
    require_named_welcome_facts,
    has_cleanup_switch_finish,
    require_not_source_code_scope,
    reminder_text,
    report_findings_direct,
    require_probe_finding,
    require_short_reminder,
    require_stored_on_level,
    require_strict_cleanup,
    require_welcome_facts_absent,
    session_start,
    session_text,
    standalone_word_present,
    stored_session_text,
    subagent_contract,
    subagent_start,
    two_sentence_probe,
    user_prompt,
    workspace_paths,
    has_light_tells,
)

_FIRE_WORDS = tuple(word for word in BANNED_VOCABULARY if word not in CONTEXT_ONLY)
MALFORMED_STDIN = "this is not a JSON object {"


# ===========================================================================
# A. Session-start emits the level-specific contract; off emits nothing
# ===========================================================================


def test_session_start_with_no_flag_emits_the_default_full_contract():
    lite_paths: list[str] = []
    lite_text = stored_session_text("lite", paths_into=lite_paths)
    with workspace() as ws:
        assert ws.read_mode_flag() is None
        result = session_start(ws)
        text = session_text(result)
        paths = workspace_paths(ws)
    assert text.strip(), "no-flag session-start emitted nothing"
    require_banned_list(text)
    require_full_scoring(text, *paths, *lite_paths)
    require_lite_omits_scoring(lite_text, text, *paths, *lite_paths)
    require_not_source_code_scope(text, *paths, *lite_paths)
    print(f"[F04] no-flag session-start len={len(text)}", flush=True)


def test_session_start_emits_a_contract_for_lite_full_and_strict():
    texts = {}
    path_bag = {}
    for level in ("lite", "full", "strict"):
        with workspace() as ws:
            ws.write_mode_flag(level)
            result = session_start(ws)
            texts[level] = session_text(result)
            path_bag[level] = workspace_paths(ws)
            print(
                f"[F04] stored {level} session-start len={len(texts[level])}",
                flush=True,
            )
    for level, text in texts.items():
        assert text.strip(), f"stored {level} session-start was empty"
        require_banned_list(text)
    paths_all = tuple(dict.fromkeys(p for bag in path_bag.values() for p in bag))
    require_full_scoring(texts["full"], *paths_all)
    require_lite_omits_scoring(texts["lite"], texts["full"], *paths_all)
    require_strict_cleanup(texts["strict"], texts["full"], *paths_all)


def test_session_start_with_off_emits_nothing_and_succeeds():
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        full_result = session_start(full_ws)
        full_text = session_text(full_result)
        full_paths = workspace_paths(full_ws)
    with workspace() as ws:
        ws.write_mode_flag("off")
        result = session_start(ws)
        require_empty_stdout(result)
    require_full_scoring(full_text, *full_paths)
    print(f"[F04] off session-start stdout_len={len(result.stdout)}", flush=True)


# ===========================================================================
# B. Banned list, not source code
# ===========================================================================


@pytest.mark.parametrize("level", ["lite", "full", "strict"])
def test_contract_contains_every_named_banned_word(level):
    with workspace() as ws:
        ws.write_mode_flag(level)
        text = session_text(session_start(ws))
    require_banned_list(text)
    print(f"[F04] {level} banned-list ok len={len(text)}", flush=True)


@pytest.mark.parametrize("level", ["lite", "full", "strict"])
def test_contract_does_not_say_it_applies_to_source_code(level):
    with workspace() as ws:
        ws.write_mode_flag(level)
        text = session_text(session_start(ws))
        paths = workspace_paths(ws)
    assert text.strip()
    require_banned_list(text)
    require_not_source_code_scope(text, *paths)
    print(f"[F04] {level} not-source-code-scope ok", flush=True)


@pytest.mark.parametrize("level", ["lite", "full", "strict"])
def test_on_level_contract_is_more_than_the_banned_word_list(level):
    with workspace() as ws:
        ws.write_mode_flag(level)
        text = session_text(session_start(ws))
    require_banned_list(text)
    print(f"[F04] {level} banned-list is the graded contract body", flush=True)


# ===========================================================================
# C. Post-write scoring targets only in full and strict
# ===========================================================================


def test_lite_contract_omits_post_write_detector_instruction():
    with workspace() as lite_ws:
        lite_ws.write_mode_flag("lite")
        lite_text = session_text(session_start(lite_ws))
        lite_paths = workspace_paths(lite_ws)
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        full_text = session_text(session_start(full_ws))
        full_paths = workspace_paths(full_ws)
    paths = tuple(dict.fromkeys((*lite_paths, *full_paths)))
    require_lite_omits_scoring(lite_text, full_text, *paths)
    print("[F04] lite omits the 40 / light-tells post-write scoring targets", flush=True)


def test_full_contract_targets_score_at_most_40():
    with workspace() as ws:
        ws.write_mode_flag("full")
        text = session_text(session_start(ws))
        paths = workspace_paths(ws)
    assert named_score_present(text, 40, *paths)
    assert standalone_word_present(text, "clean") or has_light_tells(text)
    print(f"[F04] full names 40 and clean/light-tells; len={len(text)}", flush=True)


def test_strict_contract_targets_clean_at_most_20_and_differs_from_full_by_cleanup_finish():
    with workspace() as strict_ws:
        strict_ws.write_mode_flag("strict")
        strict_text = session_text(session_start(strict_ws))
        strict_paths = workspace_paths(strict_ws)
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        full_text = session_text(session_start(full_ws))
        full_paths = workspace_paths(full_ws)
    paths = tuple(dict.fromkeys((*strict_paths, *full_paths)))
    require_strict_cleanup(strict_text, full_text, *paths)
    print("[F04] strict 20/clean and cleanup-switch finish vs full", flush=True)


# ===========================================================================
# D. One-time first-run extra; unwritable flag; later hooks see stored level
# ===========================================================================


def test_first_session_start_on_a_fresh_writable_install_prepends_the_welcome():
    with workspace() as ws:
        assert ws.read_mode_flag() is None
        first = session_text(session_start(ws))
        flag_after = ws.read_mode_flag()
        second = session_text(session_start(ws))
    assert first.strip()
    require_named_welcome_facts(first)
    require_banned_list(second)
    require_welcome_facts_absent(second)
    require_stored_on_level(flag_after)
    require_banned_list(first)
    print(
        f"[F04] first-run welcome facts present; second absent; "
        f"flag={flag_after!r}",
        flush=True,
    )


def test_second_session_start_on_the_same_config_does_not_repeat_the_welcome():
    with workspace() as ws:
        first = session_text(session_start(ws))
        second = session_text(session_start(ws))
        third = session_text(session_start(ws))
        paths = workspace_paths(ws)
    require_named_welcome_facts(first)
    require_welcome_facts_absent(second)
    require_welcome_facts_absent(third)
    require_banned_list(second)
    require_banned_list(third)
    lite_text = stored_session_text("lite")
    require_full_scoring(second, *paths)
    require_lite_omits_scoring(lite_text, second, *paths)
    print("[F04] later starts on the same config omit the named welcome facts", flush=True)


def test_after_session_start_later_hooks_see_the_stored_level():
    lite_text = stored_session_text("lite")
    full_text = stored_session_text("full")
    with workspace() as ws:
        before_prompt, _before_payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "off"}
        )
        before_sub = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
        require_empty_stdout(before_prompt)
        require_empty_stdout(before_sub)
        first = session_text(session_start(ws))
        paths = workspace_paths(ws)
        later_prompt, payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "off"}
        )
        later_sub = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
        wrapped = subagent_contract(later_sub)
    assert first.strip()
    require_short_reminder(
        later_prompt,
        level="full",
        session_text=first,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )
    require_banned_list(wrapped)
    require_full_scoring(wrapped, *paths)
    print("[F04] later hooks after first start wrap/name full", flush=True)

    with workspace() as lite_ws:
        session = session_text(session_start(lite_ws, env_updates={ENV_DEFAULT_MODE: "lite"})
        )
        lite_paths = workspace_paths(lite_ws)
        later_prompt, payload = user_prompt(
            lite_ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "off"}
        )
        later_sub = subagent_start(
            lite_ws, env_updates={ENV_DEFAULT_MODE: "off"}
        )
        wrapped = subagent_contract(later_sub)
    assert standalone_word_present(reminder_text(later_prompt), "lite")
    require_short_reminder(
        later_prompt,
        level="lite",
        session_text=session,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=lite_paths,
    )
    require_banned_list(wrapped)
    require_lite_omits_scoring(wrapped, full_text, *lite_paths)
    print("[F04] later hooks after session start stored lite", flush=True)


def test_welcome_is_not_shown_when_the_flag_cannot_be_written():
    lite_text = stored_session_text("lite")
    with workspace() as live_ws:
        live_first = session_text(session_start(live_ws))
    require_named_welcome_facts(live_first)
    with workspace() as ws:
        make_flag_unwritable(ws)
        result = session_start(ws)
        text = result.stdout_text
        paths = workspace_paths(ws)
    assert text.strip(), "unwritable session-start emitted nothing"
    require_banned_list(text)
    require_full_scoring(text, *paths)
    require_lite_omits_scoring(lite_text, text, *paths)
    require_welcome_facts_absent(text)
    print(f"[F04] unwritable len={len(text)} welcome facts absent", flush=True)


# ===========================================================================
# E. Non-command prompt-submit: short reminder naming the live level
# ===========================================================================


def test_non_command_prompt_at_full_returns_a_short_reminder_naming_full():
    lite_text = stored_session_text("lite")
    with workspace() as ws:
        ws.write_mode_flag("full")
        session = session_text(session_start(ws))
        paths = workspace_paths(ws)
        result, payload = user_prompt(ws, ordinary_prompt())
    require_banned_list(session)
    assert named_score_present(session, 40, *paths)
    require_short_reminder(
        result,
        level="full",
        session_text=session,
        full_text=session,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )


def test_prompt_reminder_names_lite_and_strict():
    lite_text = stored_session_text("lite")
    full_text = stored_session_text("full")
    for level in ("lite", "strict"):
        with workspace() as ws:
            ws.write_mode_flag(level)
            session = session_text(session_start(ws))
            paths = workspace_paths(ws)
            result, payload = user_prompt(ws, ordinary_prompt())
        require_short_reminder(
            result,
            level=level,
            session_text=session,
            full_text=full_text,
            lite_text=lite_text,
            stdin_strings=payload_string_values(payload),
            paths=paths,
        )


def test_prompt_submit_with_off_emits_nothing_and_succeeds():
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        result, _payload = user_prompt(full_ws, ordinary_prompt())
        full_text = reminder_text(result)
    with workspace() as ws:
        ws.write_mode_flag("off")
        result, payload = user_prompt(ws, ordinary_prompt())
        require_empty_stdout(result)
    assert standalone_word_present(full_text, "full"), "full reminder live baseline"
    print(
        f"[F04] off prompt-submit stdout_len={len(result.stdout)} "
        f"planted={payload_string_values(payload)[:1]!r}",
        flush=True,
    )


# ===========================================================================
# F. Subagent-start JSON object wrapping the contract
# ===========================================================================


def test_subagent_start_at_full_returns_json_envelope_with_the_contract():
    with workspace() as ws:
        ws.write_mode_flag("full")
        result = subagent_start(ws)
        wrapped = subagent_contract(result)
        paths = workspace_paths(ws)
    obj = json.loads(result.stdout_text)
    assert isinstance(obj, dict), (
        f"subagent-start JSON is {type(obj).__name__}, not an object"
    )
    require_banned_list(wrapped)
    require_full_scoring(wrapped, *paths)
    print(f"[F04] subagent full wrapped_len={len(wrapped)}", flush=True)


def test_subagent_start_at_lite_and_strict_wraps_that_level_contract():
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        full_result = subagent_start(full_ws)
        full_wrapped = subagent_contract(full_result)
        full_paths = workspace_paths(full_ws)
    full_obj = json.loads(full_result.stdout_text)
    assert isinstance(full_obj, dict), (
        f"subagent-start JSON is {type(full_obj).__name__}, not an object"
    )
    require_full_scoring(full_wrapped, *full_paths)
    assert not has_cleanup_switch_finish(full_wrapped), (
        "full subagent contract carries the cleanup-switch finish"
    )
    for level in ("lite", "strict"):
        with workspace() as ws:
            ws.write_mode_flag(level)
            result = subagent_start(ws)
            wrapped = subagent_contract(result)
            paths = workspace_paths(ws)
        obj = json.loads(result.stdout_text)
        assert isinstance(obj, dict)
        require_banned_list(wrapped)
        if level == "lite":
            require_lite_omits_scoring(wrapped, full_wrapped, *paths)
        else:
            require_strict_cleanup(wrapped, full_wrapped, *paths)
        print(f"[F04] subagent {level} wrapped_len={len(wrapped)}", flush=True)


def test_subagent_start_with_off_emits_nothing_and_succeeds():
    with workspace() as full_ws:
        full_ws.write_mode_flag("full")
        full_result = subagent_start(full_ws)
        full_wrapped = subagent_contract(full_result)
        full_paths = workspace_paths(full_ws)
    with workspace() as ws:
        ws.write_mode_flag("off")
        result = subagent_start(ws)
        require_empty_stdout(result)
    require_full_scoring(full_wrapped, *full_paths)
    print(f"[F04] off subagent stdout_len={len(result.stdout)}", flush=True)


# ===========================================================================
# G. Banned words fire an F01 family on a two-sentence probe
# ===========================================================================


@pytest.mark.parametrize("word", _FIRE_WORDS)
def test_each_standalone_banned_word_except_context_only_fires_an_f01_family(word):
    probe = two_sentence_probe(word)
    probe_run = scan_stdin(probe)
    probe_findings = report_findings_direct(probe_run)
    require_probe_finding(probe_findings)
    print(f"[F04] probe {word!r} produced a finding", flush=True)


# ===========================================================================
# H. Malformed JSON, invalid/unreadable flags, env only when nothing valid
# ===========================================================================


def test_malformed_json_still_succeeds_and_behaves_as_an_empty_object():
    full_text = stored_session_text("full")

    with workspace() as ws:
        result = session_start(ws, stdin=MALFORMED_STDIN)
        text = session_text(result)
        paths = workspace_paths(ws)
    assert result.returncode == 0
    require_banned_list(text)
    require_full_scoring(text, *paths)

    with workspace() as ws:
        ws.write_mode_flag("off")
        result = session_start(ws, stdin=MALFORMED_STDIN)
        require_empty_stdout(result)

    with workspace() as ws:
        ws.write_mode_flag("lite")
        result = session_start(ws, stdin=MALFORMED_STDIN)
        text = session_text(result)
        paths = workspace_paths(ws)
    assert result.returncode == 0
    require_lite_omits_scoring(text, full_text, *paths)

    with workspace() as ws:
        ws.write_mode_flag("strict")
        result = session_start(ws, stdin=MALFORMED_STDIN)
        text = session_text(result)
        paths = workspace_paths(ws)
    require_strict_cleanup(text, full_text, *paths)

    for level in ("full", "lite", "strict"):
        with workspace() as ws:
            ws.write_mode_flag(level)
            result = ws.invoke_hook("prompt-submit", stdin=MALFORMED_STDIN)
        assert result.returncode == 0, (
            f"malformed prompt-submit at {level} failed the host session; "
            f"exit={result.returncode} stderr={result.stderr_text!r}"
        )

    with workspace() as ws:
        ws.write_mode_flag("off")
        result = ws.invoke_hook("prompt-submit", stdin=MALFORMED_STDIN)
        require_empty_stdout(result)

    with workspace() as ws:
        ws.write_mode_flag("full")
        result = subagent_start(ws, stdin=MALFORMED_STDIN)
        full_wrapped = subagent_contract(result)
        full_paths = workspace_paths(ws)
    require_banned_list(full_wrapped)
    require_full_scoring(full_wrapped, *full_paths)
    assert not has_cleanup_switch_finish(full_wrapped), (
        "full subagent contract carries the cleanup-switch finish"
    )

    for level in ("lite", "strict"):
        with workspace() as ws:
            ws.write_mode_flag(level)
            result = subagent_start(ws, stdin=MALFORMED_STDIN)
            wrapped = subagent_contract(result)
            paths = workspace_paths(ws)
        require_banned_list(wrapped)
        if level == "lite":
            require_lite_omits_scoring(wrapped, full_wrapped, *paths)
        else:
            require_strict_cleanup(wrapped, full_wrapped, *paths)

    print("[F04] malformed JSON arms ok", flush=True)


def test_invalid_stored_level_is_ignored_and_defaults_to_full():
    bogus = runtime_token("lvl")
    with workspace() as ws:
        ws.write_mode_flag(bogus)
        result = session_start(ws)
        text = result.stdout_text
        paths = workspace_paths(ws)
    require_banned_list(text)
    require_full_scoring(text, *paths)
    print(f"[F04] invalid stored {bogus!r} defaulted to full", flush=True)

    with workspace() as ws:
        ws.write_mode_flag(bogus)
        result = session_start(ws, env_updates={ENV_DEFAULT_MODE: "lite"})
        text = result.stdout_text
        paths = workspace_paths(ws)
    full_text = stored_session_text("full")
    require_lite_omits_scoring(text, full_text, *paths)


def test_environment_level_applies_only_when_nothing_valid_is_stored():
    lite_text = stored_session_text("lite")
    full_text = stored_session_text("full")

    with workspace() as ws:
        off_s = session_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
        off_p, _ = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "off"}
        )
        off_a = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
    require_empty_stdout(off_s)
    require_empty_stdout(off_p)
    require_empty_stdout(off_a)

    with workspace() as ws:
        session = session_start(ws, env_updates={ENV_DEFAULT_MODE: "lite"})
        text = session_text(session)
        paths = workspace_paths(ws)
        prompt_r, payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "lite"}
        )
        sub_r = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "lite"})
        wrapped = subagent_contract(sub_r)
    require_lite_omits_scoring(text, full_text, *paths)
    require_short_reminder(
        prompt_r,
        level="lite",
        session_text=text,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )
    require_lite_omits_scoring(wrapped, full_text, *paths)

    with workspace() as ws:
        session = session_start(ws, env_updates={ENV_DEFAULT_MODE: "full"})
        text = session_text(session)
        paths = workspace_paths(ws)
        prompt_r, payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "full"}
        )
        sub_r = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "full"})
        wrapped = subagent_contract(sub_r)
    require_full_scoring(text, *paths)
    require_short_reminder(
        prompt_r,
        level="full",
        session_text=text,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )
    require_full_scoring(wrapped, *paths)

    with workspace() as ws:
        session = session_start(ws, env_updates={ENV_DEFAULT_MODE: "strict"})
        text = session_text(session)
        paths = workspace_paths(ws)
        prompt_r, payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "strict"}
        )
        sub_r = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "strict"})
        wrapped = subagent_contract(sub_r)
    require_strict_cleanup(text, full_text, *paths)
    require_short_reminder(
        prompt_r,
        level="strict",
        session_text=text,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )
    require_strict_cleanup(wrapped, full_text, *paths)

    for level in ("lite", "strict"):
        with workspace() as ws:
            start = session_start(ws, env_updates={ENV_DEFAULT_MODE: level})
            start_text = session_text(start)
            paths = workspace_paths(ws)
            prompt_r, payload = user_prompt(
                ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: None}
            )
            sub_r = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: None})
            wrapped = subagent_contract(sub_r)
        require_short_reminder(
            prompt_r,
            level=level,
            session_text=start_text,
            full_text=full_text,
            lite_text=lite_text,
            stdin_strings=payload_string_values(payload),
            paths=paths,
        )
        if level == "lite":
            require_lite_omits_scoring(wrapped, full_text, *paths)
        else:
            require_strict_cleanup(wrapped, full_text, *paths)

    with workspace() as ws:
        ws.write_mode_flag("full")
        session = session_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
        text = session_text(session)
        paths = workspace_paths(ws)
        prompt_r, payload = user_prompt(
            ws, ordinary_prompt(), env_updates={ENV_DEFAULT_MODE: "off"}
        )
        sub_r = subagent_start(ws, env_updates={ENV_DEFAULT_MODE: "off"})
        wrapped = subagent_contract(sub_r)
    assert text.strip(), "stored full plus env off emptied session-start"
    require_full_scoring(text, *paths)
    require_short_reminder(
        prompt_r,
        level="full",
        session_text=text,
        full_text=full_text,
        lite_text=lite_text,
        stdin_strings=payload_string_values(payload),
        paths=paths,
    )
    require_full_scoring(wrapped, *paths)
    print("[F04] env vs stored arms ok", flush=True)


def test_unreadable_mode_flag_still_succeeds():
    with workspace() as ws:
        make_flag_unreadable(ws)
        result = session_start(ws)
        text = session_text(result)
        paths = workspace_paths(ws)
    assert result.returncode == 0
    require_banned_list(text)
    require_full_scoring(text, *paths)

    with workspace() as ws:
        make_flag_unreadable(ws)
        result = session_start(ws, env_updates={ENV_DEFAULT_MODE: "lite"})
        text = session_text(result)
        paths = workspace_paths(ws)
    full_text = stored_session_text("full")
    require_lite_omits_scoring(text, full_text, *paths)
    print("[F04] unreadable flag defaults / env ok", flush=True)


# ===========================================================================
# I. Ledger older than seven days is gone by a later session
# ===========================================================================


def test_session_start_drops_a_ledger_older_than_seven_days():
    day = 24 * 3600
    with workspace() as ws:
        gone = ws.config_dir / f"{LEDGER_PREFIX}-gone.json"
        gone.write_text("[]", encoding="utf-8")
        now = time.time()
        os.utime(gone, (now - 8 * day, now - 8 * day))
        before = ledger_paths(ws.config_dir)
        assert gone in before, (
            "positive control: observer does not see the ledger the test just wrote"
        )
        session_start(ws)
        after = set(ledger_paths(ws.config_dir))
        assert gone not in after, (
            "ledger older than seven days remained after session-start"
        )
    print("[F04] ledger older than seven days gone vs pre-start listing", flush=True)


# ===========================================================================
# J. Init export is portable; hooks open no network connection
# ===========================================================================


def test_init_export_omits_detector_path_and_user_name():
    with workspace() as ws:
        _result, _payload = user_prompt(ws, "/prosecheck init")
        exported = ws.path / "AGENTS.md"
        assert exported.is_file(), (
            "init did not write the exported contract for other agents"
        )
        text = exported.read_text(encoding="utf-8")
    require_exported_contract_omits_machine_identity(text)
    print(
        f"[F04] init export len={len(text)} omits detector path and user name",
        flush=True,
    )


def test_contract_hooks_open_no_connection_to_a_proxy_sink():
    proxy_env_keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    with workspace() as ws:
        ws.write_mode_flag("full")
        with proxy_sink() as sink:
            with hook_connect_observer() as observer:
                before_sink = sink.n_connections
                before_obs = observer.n_connects
                env = {key: sink.url for key in proxy_env_keys}
                env.update(observer.env_updates)
                session = session_start(ws, env_updates=env)
                prompt_r, _payload = user_prompt(
                    ws, ordinary_prompt(), env_updates=env
                )
                sub_r = subagent_start(ws, env_updates=env)
                session_text_ = session_text(session)
                prompt_text = reminder_text(prompt_r)
                wrapped = subagent_contract(sub_r)
                assert session_text_.strip()
                assert standalone_word_present(prompt_text, "full")
                require_banned_list(wrapped)
                after_sink = sink.n_connections
                after_obs = observer.n_connects
                print(
                    f"[F04] proxy connects={after_sink - before_sink} "
                    f"observer connects={after_obs - before_obs}",
                    flush=True,
                )
                assert after_sink == before_sink
                assert after_obs == before_obs, (
                    "session-start / prompt-submit / subagent-start opened a "
                    "network connection (including clients that ignore proxy env)"
                )
                sink.fire_positive_control()
                assert sink.n_connections > after_sink
                host, port_s = sink.hostport.split(":")
                observer.fire_positive_control(host, int(port_s))
