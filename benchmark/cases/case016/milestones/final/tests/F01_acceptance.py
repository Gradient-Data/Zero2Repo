# feature: F01
"""Acceptance tests for the local detector scan, 0–100 score, and five bands."""

from __future__ import annotations

import json
import os
import zipfile

import pytest

from _harness import HarnessError, invoke, workspace
from F01_helpers import (
    PARALLELISM_17_KEY,
    TAILING_17_KEY,
    require_member,
    require_absent_member,
    EMPTY_INPUT_ERROR,
    EXIT_EMPTY_INPUT,
    EXIT_UNKNOWN_OPTION,
    EXIT_UNREADABLE,
    HELP_FLAG,
    HELP_SHORT,
    INTERVAL_FLAG,
    INTERVAL_KEY,
    TRUNCATED_KEY,
    UNKNOWN_OPTION_WORDS,
    UNREADABLE_ERROR_PREFIX,
    USAGE_SYNOPSIS,
    failure_record,
    is_unreadable_error,
    CORE_SLOTS,
    binding,
    bind_character_layer_slot,
    lookalike_arms,
    metrics_from_report,
    nonstandard_space_arms,
    structured_report,
    zero_width_arms,
    AI_REGISTER,
    HEDGE_STACK,
    HUMANIZED_CODING,
    ISOLATED_DELVE,
    NO_DETECTOR,
    OPENER_BLOCK,
    PLACEHOLDER,
    PLACEHOLDER_TWIN,
    RESIN_PARALLELISM_17,
    RESIN_WITHOUT_PARALLELISM,
    RHYTHM_CLASS,
    SCAN_CAP,
    SHORT_FACTUAL,
    SHORT_FACTUAL_TWIN,
    SHORT_SLOP,
    SHORT_SLOP_TWIN,
    SNOW_AND_ROAD,
    STACKED_VOCAB_FIRE,
    TAG_BLOCK_62,
    TAILING_NEGATION_17,
    TAILING_NEGATION_WITHOUT,
    UNDERSCOPING_16,
    TRACKING_OTHER_DOMAIN,
    TRACKING_URL,
    TRACKING_URL_PERIOD,
    WRITING_ADVICE,
    assert_band_agrees_with_score,
    band_of,
    bind_core_metric_paths,
    bind_invisible_count,
    bind_mixed_script_count,
    bind_nonstandard_space_count,
    catalogue_numbers,
    confidence_of,
    empty_input_identity,
    error_points_toward_help,
    finding_count_of,
    hit_count,
    interval_flag_from_usage,
    interval_present,
    invisible_count_of,
    latin_homoglyph,
    mixed_script_count_of,
    neutral_words,
    nonstandard_space_count_of,
    pad_human,
    padding_of_length,
    proxy_sink,
    reason_of,
    require_absent_finding,
    require_finding,
    require_no_traceback,
    require_stdout_utf8,
    require_structured_failure,
    require_success_report,
    structured_error_mapping,
    require_usage_message,
    rhythm_uniform_paragraphs,
    runtime_twin,
    sample_list,
    samples_drawn_from,
    scan_path,
    scan_stdin,
    scanned_of,
    score_moving_numbers,
    score_of,
    stderr_states_one_file_at_a_time,
    multi_file_notice_lines,
    strip_error_covariates,
    strip_paths_from_stderr,
    too_few_sentences_stated,
    bind_window_mark,
    window_is_longer,
    window_is_not_longer,
    window_mark_of,
    unicode_len,
    usage_from_help,
    usage_names_concepts,
    usage_names_end_of_options_double_dash,
    usage_names_single_file_operand,
    zw_split,
    advice_does_not_move_score,
    band_named_for_score,
    require_character_layer_counts,
)


# ===========================================================================
# A. Structured report
# ===========================================================================


def test_file_and_stdin_agree_on_short_factual_report():
    stdin_r = scan_stdin(SHORT_FACTUAL)
    f_findings, f_metrics = require_success_report(
        stdin_r, input_chars=unicode_len(SHORT_FACTUAL)
    )
    with workspace() as ws:
        ws.write("note.txt", SHORT_FACTUAL)
        file_r = scan_path(ws, "note.txt")
    p_findings, p_metrics = require_success_report(
        file_r, input_chars=unicode_len(SHORT_FACTUAL)
    )
    print("[F01] file vs stdin on short factual", flush=True)
    # L95: readable non-empty extracted prose prints a structured
    # report with findings and metrics and exits successfully.
    assert stdin_r.returncode == 0
    assert file_r.returncode == 0
    assert f_findings is not None and p_findings is not None
    assert f_metrics is not None and p_metrics is not None
    assert score_of(f_metrics, findings=f_findings) == score_of(
        p_metrics, findings=p_findings
    )
    assert band_of(f_metrics) == band_of(p_metrics)
    assert confidence_of(f_metrics) == confidence_of(p_metrics)
    assert catalogue_numbers(f_findings) == catalogue_numbers(p_findings)


def test_metrics_include_named_fields_on_success():
    result = scan_stdin(SHORT_FACTUAL)
    findings, metrics = require_success_report(
        result, input_chars=unicode_len(SHORT_FACTUAL)
    )
    # L95: structured success report (findings + metrics) and a zero exit.
    assert result.returncode == 0
    assert findings is not None
    assert metrics is not None
    band = band_of(metrics)
    score = score_of(metrics, findings=findings)
    conf = confidence_of(metrics)
    scanned = scanned_of(metrics, chars=unicode_len(SHORT_FACTUAL))
    n_findings = len(findings)
    assert 0 <= score <= 100
    assert band in ("clean", "light tells", "mixed", "heavy tells", "pervasive tells")
    assert conf in ("none", "low", "moderate", "high")
    if conf != "high":
        assert str(reason_of(metrics)).strip()
    assert scanned == unicode_len(SHORT_FACTUAL)
    assert finding_count_of(metrics, findings) == n_findings
    # L97: character-layer counts are always present, including on this
    # clean factual document. Locate by bound contrast paths; do not pin
    # key names or sibling-count equality.
    invisible, space, mixed = require_character_layer_counts(metrics)
    # L97: metrics always include the two-valued longer-than-window mark.
    # A short factual document carries the "not longer" value.
    assert window_is_not_longer(metrics)
    print(
        f"[F01] character-layer counts present invisible={invisible} "
        f"space={space} mixed={mixed} window_mark={window_mark_of(metrics)!r}",
        flush=True,
    )


def test_finding_has_label_count_and_at_most_three_samples():
    text = "They delve into the old parish records after the flood receded."
    findings, _metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    rec = require_finding(findings, 1)
    # L96 / L100: a fired finding carries a human-readable label that
    # identifies the numbered kind, a hit count, and up to three samples.
    assert rec["label"]
    assert rec["number"] == 1
    assert rec["hit"] >= 1
    samples = sample_list(rec)
    assert len(samples) <= 3
    if samples:
        samples_drawn_from(samples, text)


def test_unfired_catalogue_numbers_are_omitted():
    text = "They delve into the old parish records after the flood receded."
    findings, _metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    fired = catalogue_numbers(findings)
    print(f"[F01] one-family probe fired {sorted(fired)}", flush=True)
    require_finding(findings, 1)
    assert 1 in fired
    leaked = fired & NO_DETECTOR
    assert not leaked, f"no-detector numbers appeared as findings: {sorted(leaked)}"
    # L96: catalogue numbers that did not fire are omitted. Do not pin the
    # fired set as exactly {1}. Named constructable fires whose triggers are
    # absent from this probe must not appear.
    absent_triggers = (2, 5, 6, 13, 18, 20, 21, 47, 48, 50, 63, 64, 65)
    for number in absent_triggers:
        require_absent_finding(findings, number)
        assert number not in fired


def test_nine_no_detector_numbers_never_appear_as_findings():
    # Live baselines must actually fire (no empty-corpus path).
    ai_f, _ = require_success_report(
        scan_stdin(AI_REGISTER), input_chars=unicode_len(AI_REGISTER)
    )
    slop_f, _ = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    require_finding(ai_f, 1)
    assert catalogue_numbers(ai_f), "AI-register live baseline produced no findings"
    assert catalogue_numbers(slop_f), "dense-slop live baseline produced no findings"
    corpus = [
        HUMANIZED_CODING,
        SHORT_FACTUAL,
        f"They delve into the records. I hope this helps with the draft today.",
        f"{PLACEHOLDER} see {TRACKING_URL}",
        "They launched a bold, ambitious, transformative, innovative plan.",
    ]
    seen: set[int] = catalogue_numbers(ai_f) | catalogue_numbers(slop_f)
    for text in corpus:
        findings, _metrics = require_success_report(
            scan_stdin(text), input_chars=unicode_len(text)
        )
        seen |= catalogue_numbers(findings)
    print(f"[F01] constructable corpus fired {sorted(seen)}", flush=True)
    assert seen, "constructable corpus produced no machine-checked findings"
    leaked = seen & NO_DETECTOR
    assert not leaked, f"no-detector numbers appeared as findings: {sorted(leaked)}"


def test_sample_list_is_capped_and_hit_count_exceeds_sample_length_on_repeats():
    one = "They delve into the old parish records after the flood receded."
    nine = " ".join(["They delve into the records."] * 9)
    one_f, _ = require_success_report(scan_stdin(one), input_chars=unicode_len(one))
    nine_f, _ = require_success_report(scan_stdin(nine), input_chars=unicode_len(nine))
    rec_one = require_finding(one_f, 1)
    rec_nine = require_finding(nine_f, 1)
    one_samples = sample_list(rec_one)
    nine_samples = sample_list(rec_nine)
    assert len(one_samples) <= 3
    assert len(nine_samples) <= 3
    samples_drawn_from(nine_samples, nine)
    samples_drawn_from(one_samples, one)
    assert hit_count(rec_nine) >= 1
    assert hit_count(rec_one) >= 1
    print(
        f"[F01] many-repeat count={hit_count(rec_nine)} one-hit={hit_count(rec_one)} "
        f"samples={len(nine_samples)}",
        flush=True,
    )


# ===========================================================================
# B. Bands
# ===========================================================================


def test_band_matches_documented_range_on_named_oracles():
    fact_f, fact_m = require_success_report(
        scan_stdin(SHORT_FACTUAL), input_chars=unicode_len(SHORT_FACTUAL)
    )
    fact_score = score_of(fact_m, findings=fact_f)
    fact_band = band_of(fact_m)
    assert fact_score <= 40
    assert fact_band in ("clean", "light tells")
    assert_band_agrees_with_score(fact_m, findings=fact_f)
    assert fact_band == band_named_for_score(fact_score)

    two = f"Please see the report {PLACEHOLDER} here: {TRACKING_URL}"
    two_f, two_m = require_success_report(
        scan_stdin(two), input_chars=unicode_len(two)
    )
    two_score = score_of(two_m, findings=two_f)
    two_band = band_of(two_m)
    assert two_score >= 65
    assert two_band in ("heavy tells", "pervasive tells")
    assert two_band not in ("clean", "light tells", "mixed")
    assert_band_agrees_with_score(two_m, findings=two_f)
    assert two_band == band_named_for_score(two_score)

    slop_f, slop_m = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    slop_score = score_of(slop_m, findings=slop_f)
    slop_band = band_of(slop_m)
    assert slop_score >= fact_score + 20
    if 41 <= slop_score <= 60:
        assert slop_band == "mixed"
    assert_band_agrees_with_score(slop_m, findings=slop_f)
    assert slop_band == band_named_for_score(slop_score)

    # L98 five bands as ranges of the score, including 81–100 → pervasive tells.
    # Stack named decisive + vocabulary fires so a score in the upper ranges
    # is observed; do not pin a product-specific band spelling.
    high = (
        f"Please see the report {PLACEHOLDER} here: {TRACKING_URL} "
        "I hope this helps. Great question! As of my last training the lock "
        "had not been rebuilt. Revenue rose oai_citation last year and "
        "citeturn0search2 confirms it. The p\u0430ssword field is wr\u043eng. "
        "They delve tapestry pivotal showcase seamless in one line.\n\n"
        + rhythm_uniform_paragraphs(8)
    )
    high_f, high_m = require_success_report(
        scan_stdin(high), input_chars=unicode_len(high)
    )
    high_score = score_of(high_m, findings=high_f)
    high_band = band_of(high_m)
    assert_band_agrees_with_score(high_m, findings=high_f)
    assert high_band == band_named_for_score(high_score)
    print(
        f"[F01] L98 bands factual={fact_score}/{fact_band!r} "
        f"two={two_score}/{two_band!r} slop={slop_score}/{slop_band!r} "
        f"high={high_score}/{high_band!r}",
        flush=True,
    )
    if 0 <= high_score <= 20:
        assert high_band == "clean"
    elif 21 <= high_score <= 40:
        assert high_band == "light tells"
    elif 41 <= high_score <= 60:
        assert high_band == "mixed"
    elif 61 <= high_score <= 80:
        assert high_band == "heavy tells"
    else:
        assert 81 <= high_score <= 100
        assert high_band == "pervasive tells"


def test_every_success_report_band_agrees_with_score():
    texts = [
        SHORT_FACTUAL,
        SHORT_FACTUAL_TWIN,
        SHORT_SLOP,
        HUMANIZED_CODING,
        AI_REGISTER,
        f"{PLACEHOLDER} {TRACKING_URL}",
        "They delve into the old parish records.",
        pad_human(80),
        (
            f"Please see the report {PLACEHOLDER} here: {TRACKING_URL} "
            "I hope this helps. Great question! As of my last training the lock "
            "had not been rebuilt. Revenue rose oai_citation last year and "
            "citeturn0search2 confirms it. The p\u0430ssword field is wr\u043eng. "
            "They delve tapestry pivotal showcase seamless in one line.\n\n"
            + rhythm_uniform_paragraphs(8)
        ),
    ]
    for text in texts:
        findings, metrics = require_success_report(
            scan_stdin(text), input_chars=unicode_len(text)
        )
        assert_band_agrees_with_score(metrics, findings=findings)
        score = score_of(metrics, findings=findings)
        assert band_of(metrics) == band_named_for_score(score)
        if 81 <= score <= 100:
            assert band_of(metrics) == "pervasive tells"


# ===========================================================================
# C. Writing-advice weight zero
# ===========================================================================


def test_opener_repetition_does_not_raise_score():
    base = "Barges tied up at the old quay before the lock closed for winter."
    extra = base + " " + OPENER_BLOCK
    b_f, b_m = require_success_report(scan_stdin(base), input_chars=unicode_len(base))
    e_f, e_m = require_success_report(scan_stdin(extra), input_chars=unicode_len(extra))
    require_finding(e_f, 42)
    assert 42 in catalogue_numbers(e_f)
    moving_b = catalogue_numbers(b_f) - WRITING_ADVICE
    moving_e = catalogue_numbers(e_f) - WRITING_ADVICE
    assert moving_b == moving_e
    assert score_of(b_m, findings=b_f) == score_of(e_m, findings=e_f)


def test_hedge_stacking_does_not_raise_score():
    base = "Barges tied up at the old quay before the lock closed for winter."
    extra = base + " " + HEDGE_STACK
    b_f, b_m = require_success_report(scan_stdin(base), input_chars=unicode_len(base))
    e_f, e_m = require_success_report(scan_stdin(extra), input_chars=unicode_len(extra))
    require_finding(e_f, 54)
    assert 54 in catalogue_numbers(e_f)
    month = "In May 2025 the team shipped the lock repair on time."
    m_f, _ = require_success_report(scan_stdin(month), input_chars=unicode_len(month))
    require_absent_finding(m_f, 54)
    moving_b = catalogue_numbers(b_f) - WRITING_ADVICE
    moving_e = catalogue_numbers(e_f) - WRITING_ADVICE
    assert moving_b == moving_e
    assert score_of(b_m, findings=b_f) == score_of(e_m, findings=e_f)


def test_trailing_spaces_finding_does_not_raise_score():
    base = "Barges tied up at the old quay before the lock closed for winter."
    spaced = base + "   "
    newline = base + "\n"
    s_f, s_m = require_success_report(
        scan_stdin(spaced), input_chars=unicode_len(spaced)
    )
    n_f, n_m = require_success_report(
        scan_stdin(newline), input_chars=unicode_len(newline)
    )
    require_finding(s_f, 68)
    assert 68 in catalogue_numbers(s_f)
    require_absent_finding(n_f, 68)
    assert (catalogue_numbers(s_f) - WRITING_ADVICE) == (
        catalogue_numbers(n_f) - WRITING_ADVICE
    )
    assert score_of(s_m, findings=s_f) == score_of(n_m, findings=n_f)


def test_writing_advice_does_not_count_toward_family_diversity():
    # L101 / L103 / L108 / L126: writing-advice 42 is omitted from the
    # family set that feeds the short-document floors. The named stacked
    # vocab sentence fires 1. Adding the named "The system…" opener triple
    # fires 42 without raising the integer. Line 103's 25 is the two-family
    # floor, not a one-family cap. Line 101's stay-in-clean-or-light-tells
    # duty is isolated AI-vocabulary, not this dense stack — do not pin
    # the stack below 25 or as exactly {1}. Identify 42 by that named
    # opener input, not by a required label.
    base = STACKED_VOCAB_FIRE
    extra = base + "\n\n" + OPENER_BLOCK
    sibling = base + " I hope this helps."
    assert len(base.split()) < 120
    assert len(extra.split()) < 120
    assert len(sibling.split()) < 120
    b_f, b_m = require_success_report(scan_stdin(base), input_chars=unicode_len(base))
    e_f, e_m = require_success_report(scan_stdin(extra), input_chars=unicode_len(extra))
    s_f, s_m = require_success_report(
        scan_stdin(sibling), input_chars=unicode_len(sibling)
    )
    require_finding(b_f, 1)
    require_finding(e_f, 1)
    require_finding(e_f, 42)
    require_finding(s_f, 1)
    require_finding(s_f, 47)
    moving_s = catalogue_numbers(s_f) - WRITING_ADVICE
    b_score = score_of(b_m, findings=b_f)
    e_score = score_of(e_m, findings=e_f)
    s_score = score_of(s_m, findings=s_f)
    print(
        f"[F01] advice-diversity stacked base={b_score} extra={e_score} "
        f"sibling={s_score} moving_s={sorted(moving_s)}",
        flush=True,
    )
    assert 1 in moving_s and 47 in moving_s
    assert e_score == b_score
    assert s_score >= 25

    # Isolated one-family short arm: 1 fires; adding 42 stays at most 40
    # and does not raise the integer (L99 / L101). Adding 47 on that same
    # short base takes the two-family floor of at least 25. L103's 25 is
    # that floor, not a one-family cap — do not pin the isolated integer
    # below 25.
    iso = ISOLATED_DELVE
    iso_extra = iso + "\n\n" + OPENER_BLOCK
    iso_sib = iso + " I hope this helps."
    assert len(iso.split()) < 120
    assert len(iso_extra.split()) < 120
    assert len(iso_sib.split()) < 120
    i_f, i_m = require_success_report(scan_stdin(iso), input_chars=unicode_len(iso))
    ie_f, ie_m = require_success_report(
        scan_stdin(iso_extra), input_chars=unicode_len(iso_extra)
    )
    is_f, is_m = require_success_report(
        scan_stdin(iso_sib), input_chars=unicode_len(iso_sib)
    )
    require_finding(i_f, 1)
    require_finding(ie_f, 1)
    require_finding(ie_f, 42)
    require_finding(is_f, 1)
    require_finding(is_f, 47)
    i_score = score_of(i_m, findings=i_f)
    ie_score = score_of(ie_m, findings=ie_f)
    is_score = score_of(is_m, findings=is_f)
    print(
        f"[F01] advice-diversity isolated iso={i_score} extra={ie_score} "
        f"sibling={is_score}",
        flush=True,
    )
    assert i_score <= 40
    assert ie_score == i_score
    assert is_score >= 25
    assert ie_score <= 40
    assert band_of(ie_m) in ("clean", "light tells")


def test_listed_writing_advice_numbers_do_not_move_the_score():
    base = "Barges tied up at the old quay before the lock closed for winter."
    # L19 / L99: the graded score-neutrality duty is only the named
    # constructable probes — opener repetition (42), hedge stacking (54),
    # trailing whitespace (68), and parallelism-form 17. The other listed
    # advice numbers are inventory of the same weight-zero set, not
    # independently graded leftovers and not inputs to invent.
    held = set()
    held |= advice_does_not_move_score(base, base + " " + OPENER_BLOCK, 42)
    held |= advice_does_not_move_score(base, base + " " + HEDGE_STACK, 54)
    held |= advice_does_not_move_score(base, base + "   ", 68)
    assert {42, 54, 68} <= held
    assert held <= WRITING_ADVICE

    opener = base + " " + OPENER_BLOCK
    hedge = base + " " + HEDGE_STACK
    trail = base + "   "
    b_f, b_m = require_success_report(scan_stdin(base), input_chars=unicode_len(base))
    o_f, o_m = require_success_report(
        scan_stdin(opener), input_chars=unicode_len(opener)
    )
    h_f, h_m = require_success_report(
        scan_stdin(hedge), input_chars=unicode_len(hedge)
    )
    t_f, t_m = require_success_report(
        scan_stdin(trail), input_chars=unicode_len(trail)
    )
    base_score = score_of(b_m, findings=b_f)
    base_moving = score_moving_numbers(b_f)
    assert 42 in catalogue_numbers(o_f)
    assert 54 in catalogue_numbers(h_f)
    assert 68 in catalogue_numbers(t_f)
    assert score_moving_numbers(o_f) == base_moving
    assert score_moving_numbers(h_f) == base_moving
    assert score_moving_numbers(t_f) == base_moving
    assert score_of(o_m, findings=o_f) == base_score
    assert score_of(h_m, findings=h_f) == base_score
    assert score_of(t_m, findings=t_f) == base_score

    # L108 / L109: AI-register and dense-slop do not emit parallelism-form 17.
    # Identified by catalogue number on those named samples, not by a label
    # substring, and not by requiring 17 on the catalogue-18 not-just probe.
    for sample, label in ((AI_REGISTER, "AI-register"), (SHORT_SLOP, "dense-slop")):
        s_f, _s_m = require_success_report(
            scan_stdin(sample), input_chars=unicode_len(sample)
        )
        require_absent_member(s_f, PARALLELISM_17_KEY)
        print(f"[F01] {label} omits parallelism-form 17", flush=True)

    # L99 / L108 / L126: named resin sentence fires parallelism-form 17,
    # does not fire 18, and does not move the score when that phrasing is
    # removed. Forms are told apart by this named input plus the score
    # contrast, not by a required label wording.
    r_f, r_m = require_success_report(
        scan_stdin(RESIN_PARALLELISM_17),
        input_chars=unicode_len(RESIN_PARALLELISM_17),
    )
    w_f, w_m = require_success_report(
        scan_stdin(RESIN_WITHOUT_PARALLELISM),
        input_chars=unicode_len(RESIN_WITHOUT_PARALLELISM),
    )
    require_finding(r_f, 17)
    require_member(r_f, PARALLELISM_17_KEY)
    require_absent_finding(r_f, 18)
    assert 17 in catalogue_numbers(r_f)
    assert 18 not in catalogue_numbers(r_f)
    r_score = score_of(r_m, findings=r_f)
    w_score = score_of(w_m, findings=w_f)
    r_moving = score_moving_numbers(r_f) - {17}
    w_moving = score_moving_numbers(w_f) - {17}
    print(
        f"[F01] resin-17 score={r_score} sibling={w_score} "
        f"fired={sorted(catalogue_numbers(r_f))} sibling_fired="
        f"{sorted(catalogue_numbers(w_f))}",
        flush=True,
    )
    assert r_moving == w_moving
    assert r_score == w_score, (
        "parallelism form of 17 on the named resin probe moved the score"
    )


def test_catalogue_17_tailing_negation_moves_score_parallelism_is_advice():
    # L108 constructable fires. Forms of 17 are told apart by which named
    # input produced the finding and by whether the score moved, not by a
    # required label wording. The tailing-negation sibling is the same
    # prose with that comma-plus-"no wasted motion" tail removed — not an
    # unrelated barge sentence whose other families could move the integer.
    t_f, t_m = require_success_report(
        scan_stdin(TAILING_NEGATION_17),
        input_chars=unicode_len(TAILING_NEGATION_17),
    )
    b_f, b_m = require_success_report(
        scan_stdin(TAILING_NEGATION_WITHOUT),
        input_chars=unicode_len(TAILING_NEGATION_WITHOUT),
    )
    require_finding(t_f, 17)
    require_member(t_f, TAILING_17_KEY)
    b_score = score_of(b_m, findings=b_f)
    t_score = score_of(t_m, findings=t_f)
    moving_b = score_moving_numbers(b_f) - {17}
    moving_t = score_moving_numbers(t_f) - {17}
    print(
        f"[F01] cat17 tailing-negation without={b_score} with={t_score} "
        f"fired_t={sorted(catalogue_numbers(t_f))} "
        f"held_b={sorted(moving_b)} held_t={sorted(moving_t)}",
        flush=True,
    )
    assert moving_t == moving_b
    assert t_score != b_score

    r_f, r_m = require_success_report(
        scan_stdin(RESIN_PARALLELISM_17),
        input_chars=unicode_len(RESIN_PARALLELISM_17),
    )
    w_f, w_m = require_success_report(
        scan_stdin(RESIN_WITHOUT_PARALLELISM),
        input_chars=unicode_len(RESIN_WITHOUT_PARALLELISM),
    )
    require_finding(r_f, 17)
    require_member(r_f, PARALLELISM_17_KEY)
    require_absent_finding(r_f, 18)
    assert 18 not in catalogue_numbers(r_f)
    r_score = score_of(r_m, findings=r_f)
    w_score = score_of(w_m, findings=w_f)
    print(
        f"[F01] cat17 resin score={r_score} without={w_score} "
        f"fired={sorted(catalogue_numbers(r_f))}",
        flush=True,
    )
    assert r_score == w_score


# ===========================================================================
# D. Families vs density; floors
# ===========================================================================


def test_isolated_ai_vocabulary_stays_in_clean_or_light_tells():
    text = (
        "The lock-keeper wrote that crews delve into the silt after every flood. "
        "Stone from the old quarry still faces the western parapet."
    )
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 1)
    score = score_of(metrics, findings=findings)
    assert score <= 40
    assert band_of(metrics) in ("clean", "light tells")


def test_dense_ai_vocabulary_cluster_leaves_clean_and_light_tells():
    # L101 / L108: the named one-family stack still fires 1. Isolated
    # AI-vocabulary stays in clean / light tells (at most 40). Leaving
    # that band is the named multi-family dense-slop / AI-register
    # contrast, not a hit-count of this one-family stack — do not require
    # the repeated cluster to score above 40.
    stack = "delve tapestry pivotal showcase seamless"
    text = " ".join(f"Crews {stack} notes." for _ in range(12))
    iso = (
        "The lock-keeper wrote that crews delve into the silt after every flood. "
        "Stone from the old quarry still faces the western parapet."
    )
    d_f, d_m = require_success_report(scan_stdin(text), input_chars=unicode_len(text))
    i_f, i_m = require_success_report(scan_stdin(iso), input_chars=unicode_len(iso))
    require_finding(d_f, 1)
    require_finding(i_f, 1)
    d_score = score_of(d_m, findings=d_f)
    i_score = score_of(i_m, findings=i_f)
    print(f"[F01] dense score={d_score} isolated score={i_score}", flush=True)
    assert band_of(i_m) in ("clean", "light tells")
    assert i_score <= 40


def test_short_document_two_families_raise_floor_25():
    one = "They delve into the old parish records after the flood receded."
    two = (
        "They delve into the records. I hope this helps with the draft today."
    )
    assert len(one.split()) < 120 and len(two.split()) < 120
    o_f, o_m = require_success_report(scan_stdin(one), input_chars=unicode_len(one))
    t_f, t_m = require_success_report(scan_stdin(two), input_chars=unicode_len(two))
    require_finding(t_f, 1)
    require_finding(t_f, 47)
    one_score = score_of(o_m, findings=o_f)
    two_score = score_of(t_m, findings=t_f)
    assert two_score >= 25
    assert one_score <= 40


def test_short_document_three_families_raise_floor_45():
    three = (
        "They delve into the records. I hope this helps with the draft today. "
        "It is a world-class survey of the lock."
    )
    assert len(three.split()) < 120
    findings, metrics = require_success_report(
        scan_stdin(three), input_chars=unicode_len(three)
    )
    fired = catalogue_numbers(findings)
    moving = fired - WRITING_ADVICE
    print(f"[F01] three-family short moving={sorted(moving)}", flush=True)
    require_finding(findings, 1)
    require_finding(findings, 47)
    require_finding(findings, 3)
    assert 1 in moving and 47 in moving
    assert 3 in moving
    assert len(moving) >= 3
    assert score_of(metrics, findings=findings) >= 45


def test_two_hits_of_one_family_do_not_take_the_two_family_floor():
    # L101 / L103 / L108: two hits of AI vocabulary remain one family.
    # Named inputs: one line-108 vocab word ("delve"), then two of those
    # words ("delve" and "tapestry"). Both stay at most 40 (L101 clean /
    # light tells). A live sibling that adds chatbot artifacts (47) on
    # that one-family base takes at least 25 (L103 two-family floor).
    # Do not pin these invented crew-schedule sentences as exactly {1}.
    # Do not require the two-hit score to equal the one-hit score.
    one = "The crew will delve into the repair schedule tomorrow morning."
    two = (
        "The crew will delve into the tapestry of the repair schedule "
        "tomorrow morning."
    )
    two_fam = one + " I hope this helps."
    assert len(one.split()) < 120 and len(two.split()) < 120
    assert len(two_fam.split()) < 120
    one_f, one_m = require_success_report(
        scan_stdin(one), input_chars=unicode_len(one)
    )
    two_f, two_m = require_success_report(
        scan_stdin(two), input_chars=unicode_len(two)
    )
    fam_f, fam_m = require_success_report(
        scan_stdin(two_fam), input_chars=unicode_len(two_fam)
    )
    require_finding(one_f, 1)
    require_finding(two_f, 1)
    require_finding(fam_f, 1)
    require_finding(fam_f, 47)
    moving_fam = catalogue_numbers(fam_f) - WRITING_ADVICE
    one_score = score_of(one_m, findings=one_f)
    two_score = score_of(two_m, findings=two_f)
    fam_score = score_of(fam_m, findings=fam_f)
    print(
        f"[F01] two-hits one={one_score} two={two_score} sibling={fam_score} "
        f"moving_fam={sorted(moving_fam)}",
        flush=True,
    )
    assert 1 in moving_fam and 47 in moving_fam
    # L101: one family, even with two hits, stays in clean / light tells
    # (at most 40). A two-hit one-family score anywhere in 0–40 honours
    # that band. L103's 25 is the two-family floor on the 47 sibling, not
    # a one-family cap — do not pin these integers below 25.
    assert one_score <= 40
    assert two_score <= 40
    assert fam_score >= 25


def test_long_document_five_and_six_family_floors():
    pad = pad_human(420)
    five_bits = (
        "They delve into the records. "
        "It is a world-class survey. "
        "The latch is simple yet powerful. "
        "Studies suggest the mortar will hold. "
        "The magpie plays a vital role in its ecosystem."
    )
    six_bits = five_bits + " The beam, highlighting the old scarf joint, still sits true."
    five = pad + " " + five_bits
    six = pad + " " + six_bits
    assert len(five.split()) >= 400 and len(six.split()) >= 400
    f5, m5 = require_success_report(scan_stdin(five), input_chars=unicode_len(five))
    f6, m6 = require_success_report(scan_stdin(six), input_chars=unicode_len(six))
    moving5 = catalogue_numbers(f5) - WRITING_ADVICE
    moving6 = catalogue_numbers(f6) - WRITING_ADVICE
    print(f"[F01] long five={sorted(moving5)} six={sorted(moving6)}", flush=True)
    require_finding(f5, 1)
    require_finding(f5, 3)
    require_finding(f5, 5)
    require_finding(f5, 12)
    require_finding(f5, 14)
    require_finding(f6, 16)
    assert len(moving5) >= 5
    assert len(moving6) >= 6
    assert score_of(m5, findings=f5) >= 25
    assert score_of(m6, findings=f6) >= 45


# ===========================================================================
# E. Decisive floors
# ===========================================================================


def test_two_decisive_families_raise_score_to_at_least_65():
    text = f"Please see the report {PLACEHOLDER} here: {TRACKING_URL}"
    twin = runtime_twin("placeholder")
    for body in (text, twin):
        findings, metrics = require_success_report(
            scan_stdin(body), input_chars=unicode_len(body)
        )
        fired = catalogue_numbers(findings)
        print(f"[F01] two-decisive fired={sorted(fired)}", flush=True)
        assert 63 in fired and 65 in fired
        assert score_of(metrics, findings=findings) >= 65


def test_placeholder_plus_tracking_parameter_scores_at_least_65():
    text = f"Please see the report {PLACEHOLDER} here: {TRACKING_URL}"
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 63)
    require_finding(findings, 65)
    assert score_of(metrics, findings=findings) >= 65


def test_two_other_decisive_families_also_raise_score_to_at_least_65():
    zw = "\u200b"
    cyr = "\u0430"
    text = (
        f"The hidden{zw}mark sits in English prose. "
        f"The p{cyr}ssword field is wrong on the form."
    )
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    fired = catalogue_numbers(findings)
    print(f"[F01] 62+66 fired={sorted(fired)}", flush=True)
    assert 62 in fired and 66 in fired
    assert score_of(metrics, findings=findings) >= 65


def test_leftover_decisive_pairs_raise_score_to_at_least_65():
    # L102 leftover decisive members 13, 47, 48, 50, 64: two distinct
    # leftover families in one scan take the 65 floor. Named L108 fires,
    # not unlabeled long pads, and not a required label substring.
    pairs = (
        (
            "The List of English monarchs is a comprehensive resource for the "
            "period. I hope this helps.",
            (13, 47),
        ),
        (
            "Great question! As of my last training the lock had not been rebuilt.",
            (48, 50),
        ),
        (
            "Revenue rose oai_citation last year and citeturn0search2 confirms it. "
            "I hope this helps.",
            (64, 47),
        ),
    )
    for text, numbers in pairs:
        findings, metrics = require_success_report(
            scan_stdin(text), input_chars=unicode_len(text)
        )
        fired = catalogue_numbers(findings)
        score = score_of(metrics, findings=findings)
        print(
            f"[F01] leftover-decisive {numbers} fired={sorted(fired)} score={score}",
            flush=True,
        )
        for number in numbers:
            require_finding(findings, number)
            assert number in fired
        assert score >= 65


def test_single_decisive_at_low_or_none_does_not_take_45():
    one_ph = f"Please see the report {PLACEHOLDER} before noon today."
    two_ph = f"Please see the report {PLACEHOLDER} here: {TRACKING_URL}"
    zw = "\u200b"
    one_zw = f"The hidden{zw}mark sits in English prose near the lock."
    two_zw = (
        f"The hidden{zw}mark sits in English prose. "
        f"The p\u0430ssword field is wrong on the form."
    )
    for single, sibling, number in (
        (one_ph, two_ph, 63),
        (one_zw, two_zw, 62),
    ):
        s_f, s_m = require_success_report(
            scan_stdin(single), input_chars=unicode_len(single)
        )
        t_f, t_m = require_success_report(
            scan_stdin(sibling), input_chars=unicode_len(sibling)
        )
        s_score = score_of(s_m, findings=s_f)
        t_score = score_of(t_m, findings=t_f)
        conf = confidence_of(s_m)
        print(f"[F01] single decisive {number} score={s_score} conf={conf}", flush=True)
        require_finding(s_f, number)
        assert conf in ("none", "low")
        assert t_score >= 65

    # L102: a single decisive family at none or low does not take the 45
    # floor (floor not applied, not a cap on every such document). Witness:
    # this human-majority none/low single-decisive document is not raised
    # to 45. The high-confidence arm below shows the floor when it applies.
    pad = pad_human(80)
    gq = "Great question! " + pad
    gq_f, gq_m = require_success_report(
        scan_stdin(gq), input_chars=unicode_len(gq)
    )
    require_finding(gq_f, 48)
    gq_conf = confidence_of(gq_m)
    gq_score = score_of(gq_m, findings=gq_f)
    print(
        f"[F01] single-decisive floor-not-applied score={gq_score} conf={gq_conf}",
        flush=True,
    )
    assert gq_conf in ("none", "low")
    # L126 named none/low witness: this human-majority pad is not raised
    # to the 45 floor. That is a cap on this probe (at most 40), not on
    # the short placeholder or zero-width singles above.
    assert gq_score <= 40

    # Live baseline: the 45 floor is applied when confidence is above low.
    high = pad_human(320) + f" See {TRACKING_URL} for detail."
    assert len(high.split()) >= 300
    high_f, high_m = require_success_report(
        scan_stdin(high), input_chars=unicode_len(high)
    )
    require_finding(high_f, 65)
    assert confidence_of(high_m) == "high"
    assert score_of(high_m, findings=high_f) >= 45


def test_single_decisive_above_low_confidence_raises_at_least_45():
    moderate = (
        pad_human(160)
        + " They delve into the records. See "
        + TRACKING_URL
        + " for detail."
    )
    n_mod = len(moderate.split())
    assert 120 <= n_mod < 300
    mod_f, mod_m = require_success_report(
        scan_stdin(moderate), input_chars=unicode_len(moderate)
    )
    require_finding(mod_f, 65)
    require_finding(mod_f, 1)
    moving = catalogue_numbers(mod_f) - WRITING_ADVICE
    print(
        f"[F01] moderate single-decisive moving={sorted(moving)} words={n_mod}",
        flush=True,
    )
    assert 65 in moving and 1 in moving
    assert confidence_of(mod_m) == "moderate"

    high = pad_human(320) + f" See {TRACKING_URL} for detail."
    assert len(high.split()) >= 300
    high_f, high_m = require_success_report(
        scan_stdin(high), input_chars=unicode_len(high)
    )
    require_finding(high_f, 65)
    assert confidence_of(high_m) == "high"
    assert score_of(high_m, findings=high_f) >= 45


def test_long_human_plus_one_decisive_stays_at_most_40_with_required_confidence():
    pad = pad_human(80)
    assert 40 <= len(pad.split()) < 300
    gq = "Great question! " + pad
    url = pad + f" See {TRACKING_URL} for detail."
    gq_f, gq_m = require_success_report(
        scan_stdin(gq), input_chars=unicode_len(gq)
    )
    url_f, url_m = require_success_report(
        scan_stdin(url), input_chars=unicode_len(url)
    )
    require_finding(gq_f, 48)
    require_finding(url_f, 65)
    gq_score = score_of(gq_m, findings=gq_f)
    url_score = score_of(url_m, findings=url_f)
    gq_conf = confidence_of(gq_m)
    url_conf = confidence_of(url_m)
    print(
        f"[F01] long-human + one decisive gq={gq_score}/{gq_conf} "
        f"url={url_score}/{url_conf}",
        flush=True,
    )
    assert gq_conf != "none" and url_conf != "none"
    assert gq_conf == "low" and url_conf == "low"
    assert gq_score <= 40
    assert url_score <= 40


# ===========================================================================
# F. Human vs slop; rhythm cap
# ===========================================================================


def test_short_factual_human_stays_at_or_below_40():
    for text in (SHORT_FACTUAL, runtime_twin("factual")):
        findings, metrics = require_success_report(
            scan_stdin(text), input_chars=unicode_len(text)
        )
        score = score_of(metrics, findings=findings)
        assert score <= 40
        assert band_of(metrics) in ("clean", "light tells")


def test_short_dense_slop_outscores_factual_by_at_least_20():
    fact_f, fact_m = require_success_report(
        scan_stdin(SHORT_FACTUAL), input_chars=unicode_len(SHORT_FACTUAL)
    )
    slop_f, slop_m = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    twin_f, twin_m = require_success_report(
        scan_stdin(SHORT_SLOP_TWIN), input_chars=unicode_len(SHORT_SLOP_TWIN)
    )
    fact_score = score_of(fact_m, findings=fact_f)
    slop_score = score_of(slop_m, findings=slop_f)
    twin_score = score_of(twin_m, findings=twin_f)
    fact_words = len(SHORT_FACTUAL.split())
    slop_words = len(SHORT_SLOP.split())
    twin_words = len(SHORT_SLOP_TWIN.split())
    print(
        f"[F01] slop gap fact={fact_score} slop={slop_score} twin={twin_score} "
        f"words fact={fact_words} slop={slop_words} twin={twin_words}",
        flush=True,
    )
    assert abs(slop_words - fact_words) <= 20
    assert abs(twin_words - fact_words) <= 20
    assert slop_score >= fact_score + 20
    # PRD FP-01: the twin carries two escalating families (floor 25) while
    # the factual paragraph is clean; the 20-point gap is not a rule for it.
    assert twin_score >= 25
    assert twin_score > fact_score
    require_absent_member(slop_f, PARALLELISM_17_KEY)


def test_named_line_126_oracles_are_not_a_constant_fifty():
    # L126 / L127: the constant-50 hollow is held through the named
    # score contrasts, not through a standalone "some score is not 50"
    # check and not by forbidding a dense-slop integer of 50.
    fact_f, fact_m = require_success_report(
        scan_stdin(SHORT_FACTUAL), input_chars=unicode_len(SHORT_FACTUAL)
    )
    slop_f, slop_m = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    two = f"Please see the report {PLACEHOLDER} here: {TRACKING_URL}"
    two_f, two_m = require_success_report(
        scan_stdin(two), input_chars=unicode_len(two)
    )
    fact_score = score_of(fact_m, findings=fact_f)
    slop_score = score_of(slop_m, findings=slop_f)
    two_score = score_of(two_m, findings=two_f)
    print(
        f"[F01] L127 constant-50 hollow factual={fact_score} slop={slop_score} "
        f"two-decisive={two_score}",
        flush=True,
    )
    # L126 / L127: the three named contrasts already fail a constant-50 stub.
    # A legitimate dense-slop score of 50 is not forbidden when it still beats
    # the factual arm by 20 and the two-decisive probe is at least 65.
    assert fact_score <= 40
    assert slop_score >= fact_score + 20
    assert two_score >= 65
    require_finding(two_f, 63)
    require_finding(two_f, 65)


def test_humanized_coding_sample_has_zero_findings():
    # PRD FP-01: this plain human prose fires no family rule; with no
    # score-moving finding other than sentence-length monotony it is clean.
    findings, metrics = require_success_report(
        scan_stdin(HUMANIZED_CODING), input_chars=unicode_len(HUMANIZED_CODING)
    )
    fired = catalogue_numbers(findings)
    assert not ((fired - WRITING_ADVICE) - {40}), sorted(fired)
    assert finding_count_of(metrics, findings) == len(findings)
    assert score_of(metrics, findings=findings) <= 20
    assert band_of(metrics) == "clean"


def test_ai_register_sample_has_ten_findings_and_higher_score():
    ai_f, ai_m = require_success_report(
        scan_stdin(AI_REGISTER), input_chars=unicode_len(AI_REGISTER)
    )
    hu_f, hu_m = require_success_report(
        scan_stdin(HUMANIZED_CODING), input_chars=unicode_len(HUMANIZED_CODING)
    )
    fired = catalogue_numbers(ai_f)
    print(f"[F01] AI-register fired {sorted(fired)} n={len(ai_f) if not isinstance(ai_f, dict) else len(ai_f)}", flush=True)
    n = len(ai_f) if not isinstance(ai_f, dict) else len(ai_f)
    assert n >= 10
    for number in (1, 47, 48, 39, 51):
        require_finding(ai_f, number)
        rec = require_finding(ai_f, number)
        assert rec["number"] == number
    require_absent_member(ai_f, PARALLELISM_17_KEY)
    assert not ((catalogue_numbers(hu_f) - WRITING_ADVICE) - {40})
    slop_f, _slop_m = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    require_absent_member(slop_f, PARALLELISM_17_KEY)
    lab1 = require_finding(ai_f, 1)["label"]
    lab47 = require_finding(ai_f, 47)["label"]
    # Contract: labels are free text, but two catalogue numbers never share one.
    assert lab1 != lab47
    assert score_of(ai_m, findings=ai_f) > score_of(hu_m, findings=hu_f)


def test_rhythm_only_finding_present_cannot_exceed_40():
    # L104 / L126: pipe the named three-sentence snow-and-road document.
    # Assert a rhythm-class finding among sentence-length monotony,
    # mechanical alternation, uniform paragraph length, and contraction
    # absence, and an integer score of at most 40. Unlabeled even-length,
    # equal-paragraph, short-then-long, or contraction-absence pads are
    # not each required to fire 40/41/44/55.
    snow_f, snow_m = require_success_report(
        scan_stdin(SNOW_AND_ROAD), input_chars=unicode_len(SNOW_AND_ROAD)
    )
    snow_fired = catalogue_numbers(snow_f)
    snow_score = score_of(snow_m, findings=snow_f)
    print(
        f"[F01] snow-and-road fired={sorted(snow_fired)} score={snow_score}",
        flush=True,
    )
    assert snow_fired & RHYTHM_CLASS, (
        "named snow-and-road document did not yield a rhythm-class finding"
    )
    assert snow_score <= 40

    fact_f, fact_m = require_success_report(
        scan_stdin(SHORT_FACTUAL), input_chars=unicode_len(SHORT_FACTUAL)
    )
    slop_f, slop_m = require_success_report(
        scan_stdin(SHORT_SLOP), input_chars=unicode_len(SHORT_SLOP)
    )
    fact_score = score_of(fact_m, findings=fact_f)
    slop_score = score_of(slop_m, findings=slop_f)
    print(
        f"[F01] rhythm-cap factual={fact_score} slop={slop_score}",
        flush=True,
    )
    assert fact_score <= 40
    assert slop_score >= fact_score + 20


# ===========================================================================
# G. Confidence
# ===========================================================================


def test_confidence_none_below_40_words():
    text = neutral_words(39)
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    assert confidence_of(metrics) == "none"
    assert str(reason_of(metrics)).strip()


def test_confidence_low_below_120_words():
    none_text = neutral_words(39)
    low_text = neutral_words(40)
    _, none_m = require_success_report(
        scan_stdin(none_text), input_chars=unicode_len(none_text)
    )
    _, low_m = require_success_report(
        scan_stdin(low_text), input_chars=unicode_len(low_text)
    )
    assert confidence_of(none_m) == "none"
    assert confidence_of(low_m) == "low"
    assert str(reason_of(low_m)).strip()


def test_confidence_low_below_300_with_one_score_moving_family():
    text = (
        pad_human(200)
        + " They delve into the old parish records. "
        + OPENER_BLOCK
    )
    assert len(text.split()) < 300
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 1)
    require_finding(findings, 42)
    moving = score_moving_numbers(findings)
    print(f"[F01] one-family confidence moving={sorted(moving)}", flush=True)
    # AI vocabulary is the score-moving family the sentence adds; opener
    # repetition 42 is writing advice and does not count. Below 300 words,
    # one score-moving family is `low`; should the implementation also
    # count another score-moving family on the pad, the same rule makes
    # the document `moderate`. Either way a reason is given.
    assert 1 in moving
    expected = "low" if moving == {1} else "moderate"
    assert confidence_of(metrics) == expected, (sorted(moving), confidence_of(metrics))
    assert str(reason_of(metrics)).strip()


def test_confidence_moderate_below_300_with_more_families():
    text = (
        pad_human(200)
        + " They delve into the records. I hope this helps with the draft today."
    )
    assert len(text.split()) < 300
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    moving = catalogue_numbers(findings) - WRITING_ADVICE
    assert 1 in moving and 47 in moving
    assert confidence_of(metrics) == "moderate"
    assert str(reason_of(metrics)).strip()


def test_confidence_high_at_300_words():
    text = neutral_words(300)
    _findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    assert confidence_of(metrics) == "high"


# ===========================================================================
# H. Non-prose masks
# ===========================================================================


def test_fenced_delve_does_not_fire_but_delve_after_fence_does():
    inner = "```\ndelve\nI hope this helps\n```"
    masked = inner + "\n\nThey delve into the records after."
    findings, _ = require_success_report(
        scan_stdin(masked), input_chars=unicode_len(masked)
    )
    require_finding(findings, 1)
    # The after-fence delve is the live baseline; inside-fence delve must not
    # be an extra hit that would appear without the after sentence.
    only_fence = "```\ndelve\nI hope this helps\n```\n\nStone sat by the river wall."
    quiet, _ = require_success_report(
        scan_stdin(only_fence), input_chars=unicode_len(only_fence)
    )
    require_absent_finding(quiet, 1)
    require_absent_finding(quiet, 47)
    assert 1 in catalogue_numbers(findings)
    assert 1 not in catalogue_numbers(quiet)
    assert 47 not in catalogue_numbers(quiet)


def test_nested_longer_opening_fence_keeps_inner_example_out():
    inner_lens = (3, 4)
    for inner_n, extra in zip(inner_lens, (1, 2)):
        inner = "`" * inner_n
        outer = "`" * (inner_n + extra)
        body = (
            f"{outer}\n"
            f"{inner}\n"
            f"delve\n"
            f"I hope this helps\n"
            f"{inner}\n"
            f"{outer}\n\n"
            "They delve into the records after."
        )
        print(f"[F01] nested fence inner={inner_n} outer={inner_n + extra}", flush=True)
        findings, _ = require_success_report(
            scan_stdin(body), input_chars=unicode_len(body)
        )
        require_finding(findings, 1)
        quiet_only = (
            f"{outer}\n{inner}\ndelve\nI hope this helps\n{inner}\n{outer}\n\n"
            "Stone sat by the river wall."
        )
        quiet, _ = require_success_report(
            scan_stdin(quiet_only), input_chars=unicode_len(quiet_only)
        )
        require_absent_finding(quiet, 1)
        require_absent_finding(quiet, 47)
        assert 1 in catalogue_numbers(findings)
        assert 1 not in catalogue_numbers(quiet)
        assert 47 not in catalogue_numbers(quiet)


def test_indented_code_block_does_not_fire():
    body = "\n    delve\n    I hope this helps\n\nThey delve into the records after."
    findings, _ = require_success_report(
        scan_stdin(body), input_chars=unicode_len(body)
    )
    require_finding(findings, 1)
    quiet = "\n    delve\n    I hope this helps\n\nStone sat by the river wall."
    q_f, _ = require_success_report(scan_stdin(quiet), input_chars=unicode_len(quiet))
    require_absent_finding(q_f, 1)
    require_absent_finding(q_f, 47)
    assert 1 in catalogue_numbers(findings)
    assert 1 not in catalogue_numbers(q_f)
    assert 47 not in catalogue_numbers(q_f)


def test_consecutive_blockquotes_do_not_fire():
    body = (
        "> delve into the notes\n"
        "> I hope this helps\n\n"
        "They delve into the records after."
    )
    findings, _ = require_success_report(
        scan_stdin(body), input_chars=unicode_len(body)
    )
    require_finding(findings, 1)
    quiet = "> delve into the notes\n> I hope this helps\n\nStone sat by the river wall."
    q_f, _ = require_success_report(scan_stdin(quiet), input_chars=unicode_len(quiet))
    require_absent_finding(q_f, 1)
    require_absent_finding(q_f, 47)
    assert 1 in catalogue_numbers(findings)
    assert 1 not in catalogue_numbers(q_f)
    assert 47 not in catalogue_numbers(q_f)


def test_markdown_table_and_badge_and_front_matter_do_not_fire():
    # A table valid under the common (GFM) specification: header, delimiter, body.
    table = "| col | delve |\n| --- | --- |\n| row | I hope this helps |\n"
    badge = "[![delve I hope this helps](https://img.example/b.svg)](https://example.com)\n"
    front = "---\ntitle: delve\nnote: I hope this helps\n---\n"
    after = "They delve into the records after."
    filler = "Stone sat by the river wall."
    for mask, name in (
        (table, "table"),
        (badge, "badge"),
        (front, "front-matter"),
    ):
        quiet = mask + "\n" + filler
        live = mask + "\n" + after
        print(f"[F01] mask {name}", flush=True)
        q_f, _ = require_success_report(
            scan_stdin(quiet), input_chars=unicode_len(quiet)
        )
        l_f, _ = require_success_report(
            scan_stdin(live), input_chars=unicode_len(live)
        )
        require_absent_finding(q_f, 1)
        require_absent_finding(q_f, 47)
        require_finding(l_f, 1)
        assert 1 not in catalogue_numbers(q_f)
        assert 47 not in catalogue_numbers(q_f)
        assert 1 in catalogue_numbers(l_f)


def test_indented_paragraph_continuation_still_fires():
    text = (
        "The lock-keeper wrote that crews\n"
        "    delve into the silt after every flood."
    )
    findings, _ = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 1)
    assert 1 in catalogue_numbers(findings)


def test_second_named_fire_inside_each_mask_also_stays_quiet():
    second = "I hope this helps"
    masks = {
        "fence": f"```\ndelve\n{second}\n```\n",
        "indent": f"\n    delve\n    {second}\n",
        "quote": f"> delve\n> {second}\n",
        "table": "| x | delve |\n| --- | --- |\n| y | I hope this helps |\n",
        "badge": "[![delve I hope this helps](https://img.example/b.svg)](https://example.com)\n",
        "yaml": "---\ntitle: delve\nnote: I hope this helps\n---\n",
    }
    filler = "Stone sat by the river wall."
    after_delve = "They delve into the records after."
    after_helps = "I hope this helps with the draft today."
    # Unmasked 47 is the live sibling that fails an implementation whose
    # quiet arms stay quiet only because catalogue 47 never fires at all.
    unmasked = after_helps
    u_f, _ = require_success_report(
        scan_stdin(unmasked), input_chars=unicode_len(unmasked)
    )
    require_finding(u_f, 47)
    assert 47 in catalogue_numbers(u_f)
    for name, mask in masks.items():
        quiet = mask + "\n" + filler
        live_delve = mask + "\n" + after_delve
        live_47 = mask + "\n" + after_helps
        print(f"[F01] second-fire mask {name}", flush=True)
        q_f, _ = require_success_report(
            scan_stdin(quiet), input_chars=unicode_len(quiet)
        )
        d_f, _ = require_success_report(
            scan_stdin(live_delve), input_chars=unicode_len(live_delve)
        )
        h_f, _ = require_success_report(
            scan_stdin(live_47), input_chars=unicode_len(live_47)
        )
        require_absent_finding(q_f, 1)
        require_absent_finding(q_f, 47)
        require_finding(d_f, 1)
        require_finding(h_f, 47)
        assert 1 not in catalogue_numbers(q_f)
        assert 47 not in catalogue_numbers(q_f)
        assert 1 in catalogue_numbers(d_f)
        assert 47 in catalogue_numbers(h_f)


# ===========================================================================
# I. Zero-width split and homoglyph
# ===========================================================================


def test_banned_word_split_only_by_zero_width_still_fires():
    plain = "They delve into the old parish records after the flood receded."
    split = "They " + zw_split("delve") + " into the old parish records after the flood receded."
    p_f, _ = require_success_report(scan_stdin(plain), input_chars=unicode_len(plain))
    s_f, _ = require_success_report(scan_stdin(split), input_chars=unicode_len(split))
    require_finding(p_f, 1)
    require_finding(s_f, 1)
    assert 1 in catalogue_numbers(p_f)
    assert 1 in catalogue_numbers(s_f)


def test_second_banned_word_split_only_by_zero_width_still_fires():
    word = "showcase"
    plain = f"They {word} the old parish records after the flood receded."
    split = f"They {zw_split(word)} the old parish records after the flood receded."
    p_f, _ = require_success_report(scan_stdin(plain), input_chars=unicode_len(plain))
    s_f, _ = require_success_report(scan_stdin(split), input_chars=unicode_len(split))
    require_finding(p_f, 1)
    require_finding(s_f, 1)
    assert 1 in catalogue_numbers(p_f)
    assert 1 in catalogue_numbers(s_f)


def test_latin_run_homoglyph_fires_66_and_the_ascii_vocabulary_finding():
    ascii_w = "showcase"
    dirty = latin_homoglyph(ascii_w)
    plain = f"They {ascii_w} the old parish records after the flood receded."
    mixed = f"They {dirty} the old parish records after the flood receded."
    p_f, _ = require_success_report(scan_stdin(plain), input_chars=unicode_len(plain))
    m_f, _ = require_success_report(scan_stdin(mixed), input_chars=unicode_len(mixed))
    require_finding(p_f, 1)
    require_finding(m_f, 1)
    require_finding(m_f, 66)
    assert 1 in catalogue_numbers(p_f)
    assert 1 in catalogue_numbers(m_f)
    assert 66 in catalogue_numbers(m_f)


def test_latin_run_homoglyph_moves_mixed_script_count():
    # Same prose on both arms; only the second carries the lookalike letters.
    plain, mixed = lookalike_arms()
    p_f, p_m = require_success_report(
        scan_stdin(plain), input_chars=unicode_len(plain)
    )
    m_f, m_m = require_success_report(
        scan_stdin(mixed), input_chars=unicode_len(mixed)
    )
    require_finding(m_f, 66)
    assert mixed_script_count_of(m_m) > mixed_script_count_of(p_m)


# ===========================================================================
# J. Constructable fires / non-fires
# ===========================================================================


FIRE_CASES = [
    ("vocab-stack", "They delve tapestry pivotal showcase seamless in one line.", (1,)),
    (
        "dialect",
        "That genuinely fascinating trick is a game-changer that can supercharge the work.",
        (2,),
    ),
    ("promo", "A world-class inn nestled in the heart of the valley.", (3,)),
    ("simple-yet", "The latch is simple yet powerful in daily use.", (5,)),
    (
        "adj-stack",
        "They launched a bold, ambitious, transformative, innovative plan.",
        (6,),
    ),
    (
        "synonym",
        "The protagonist faces many challenges. The main character must overcome obstacles. "
        "The central figure eventually triumphs. The hero returns home.",
        (8,),
    ),
    (
        "synonym-companies",
        "Several companies launched new products this quarter. Other firms followed. "
        "Many organizations had to retool. Most businesses adapted.",
        (8,),
    ),
    ("vague", "Studies suggest the mortar will hold. Experts argue otherwise.", (12,)),
    (
        "article-title",
        "The List of English monarchs is a comprehensive resource for the period.",
        (13,),
    ),
    (
        "ecosystem",
        "The Eurasian magpie plays a vital role in its ecosystem along the river.",
        (14,),
    ),
    (
        "humble-mighty",
        "The story runs from the humble hand-forged nail to the mighty beam engine.",
        (15,),
    ),
    ("ing-tail", "The beam sits true, highlighting the old scarf joint.", (16,)),
    ("ing-underscoring", UNDERSCOPING_16, (16,)),
    ("paving", "The repair finished on time, paving the way for the next season.", (21,)),
    ("tailing-neg", "The joint is tight, no wasted motion in the crew's work.", (17,)),
    ("resin-parallelism-17", RESIN_PARALLELISM_17, (17,)),
    (
        "not-just",
        "It's not just a hobby, it's a craft. No fluff, just results on the quay.",
        (18,),
    ),
    ("pivot", "It's worth noting that the lock still opens at dawn.", (20,)),
    (
        "chatbot",
        "I hope this helps. As an AI language model I must be careful. Here is a draft.",
        (47,),
    ),
    ("cutoff", "As of my last training the lock had not been rebuilt.", (50,)),
    (
        "copula",
        "The bridge serves as a crossing and stands as a testament to the masons.",
        (51, 10),
    ),
    ("hedge", HEDGE_STACK, (54,)),
    ("placeholder", f"Write to {PLACEHOLDER} or {PLACEHOLDER_TWIN} today.", (63,)),
    (
        "ref-markup",
        "Revenue rose oai_citation last year and citeturn0search2 confirms it.",
        (64,),
    ),
    ("utm", f"Full writeup at {TRACKING_URL} today.", (65,)),
    ("utm-period", f"Read the rest at {TRACKING_URL_PERIOD}", (65,)),
    ("homoglyph", "The p\u0430ssword field is wr\u043eng.", (66,)),
    ("zw", "Hidden\u200bword in English prose near the lock.", (62,)),
    ("tag-block", TAG_BLOCK_62, (62,)),
    ("nbsp", "Two\u00a0words sit on the page.", (67,)),
    ("trailing", "Pasted text with stray trailing spaces.   ", (68,)),
    (
        "transition",
        "Additionally the wall held. Furthermore the pier held. Moreover the deck held.",
        (37,),
    ),
]


@pytest.mark.parametrize("name,text,numbers", FIRE_CASES, ids=[c[0] for c in FIRE_CASES])
def test_constructable_fires_match_named_probes(name, text, numbers):
    findings, metrics = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    print(f"[F01] fire {name} -> {sorted(catalogue_numbers(findings))}", flush=True)
    for number in numbers:
        require_finding(findings, number)
        assert number in catalogue_numbers(findings)
    # L108: forms of 17 vs 18 are told apart by which named input fired
    # and whether the score moved, not by a required label wording.
    if name == "resin-parallelism-17":
        require_member(findings, PARALLELISM_17_KEY)
        require_absent_finding(findings, 18)
        assert 18 not in catalogue_numbers(findings)
        w_f, w_m = require_success_report(
            scan_stdin(RESIN_WITHOUT_PARALLELISM),
            input_chars=unicode_len(RESIN_WITHOUT_PARALLELISM),
        )
        r_score = score_of(metrics, findings=findings)
        w_score = score_of(w_m, findings=w_f)
        r_moving = (catalogue_numbers(findings) - WRITING_ADVICE) - {17}
        w_moving = (catalogue_numbers(w_f) - WRITING_ADVICE) - {17}
        assert r_moving == w_moving
        assert r_score == w_score
    if name == "not-just":
        require_finding(findings, 18)
        assert 18 in catalogue_numbers(findings)
        # Named 18 fire, not the parallelism-form 17 fire (that fire is
        # the resin sentence: 17, not 18, score-neutral). Do not require
        # 17 on this probe and do not classify the form by label wording.
        r_f, _r_m = require_success_report(
            scan_stdin(RESIN_PARALLELISM_17),
            input_chars=unicode_len(RESIN_PARALLELISM_17),
        )
        require_finding(r_f, 17)
        require_member(r_f, PARALLELISM_17_KEY)
        require_absent_finding(r_f, 18)
        assert 17 in catalogue_numbers(r_f)
        assert 18 not in catalogue_numbers(r_f)
    if name == "tailing-neg":
        # Same prose with the comma-plus-"no wasted motion" tail removed.
        # Presence of 17 is told apart by this named input. Score movement
        # is the dedicated tailing-negation test, with other score-moving
        # findings held equal.
        w_f, _w_m = require_success_report(
            scan_stdin(TAILING_NEGATION_WITHOUT),
            input_chars=unicode_len(TAILING_NEGATION_WITHOUT),
        )
        require_finding(findings, 17)
        require_member(findings, TAILING_17_KEY)
        require_absent_member(w_f, TAILING_17_KEY)
        require_absent_finding(w_f, 17)
        assert 17 in catalogue_numbers(findings)
        assert 17 not in catalogue_numbers(w_f)


def test_named_catalogue_18_probes_are_not_the_parallelism_form_17_fire():
    # L108: “it’s not just X, it’s Y” and “No fluff, just results” fire 18
    # and are not the resin parallelism-form 17 fire. Forms are told apart
    # by which named input fired, not by a required label wording.
    not_just = "It's not just a hobby, it's a craft on the quay."
    fluff = "No fluff, just results on the quay."
    for body in (not_just, fluff):
        findings, _metrics = require_success_report(
            scan_stdin(body), input_chars=unicode_len(body)
        )
        require_finding(findings, 18)
        assert 18 in catalogue_numbers(findings)
    r_f, r_m = require_success_report(
        scan_stdin(RESIN_PARALLELISM_17),
        input_chars=unicode_len(RESIN_PARALLELISM_17),
    )
    w_f, w_m = require_success_report(
        scan_stdin(RESIN_WITHOUT_PARALLELISM),
        input_chars=unicode_len(RESIN_WITHOUT_PARALLELISM),
    )
    require_finding(r_f, 17)
    require_member(r_f, PARALLELISM_17_KEY)
    require_absent_finding(r_f, 18)
    assert 17 in catalogue_numbers(r_f)
    assert 18 not in catalogue_numbers(r_f)
    assert score_of(r_m, findings=r_f) == score_of(w_m, findings=w_f)


def test_comma_plus_underscoring_fires_superficial_ing_tail():
    # L108: a comma plus "underscoring" fires superficial -ing tail clauses (16).
    findings, _metrics = require_success_report(
        scan_stdin(UNDERSCOPING_16), input_chars=unicode_len(UNDERSCOPING_16)
    )
    print(
        f"[F01] underscoring-16 fired={sorted(catalogue_numbers(findings))}",
        flush=True,
    )
    require_finding(findings, 16)
    assert 16 in catalogue_numbers(findings)


def test_tag_block_in_english_prose_fires_invisible_characters():
    # L108: a TAG-block in English prose fires invisible/zero-width characters (62).
    findings, _metrics = require_success_report(
        scan_stdin(TAG_BLOCK_62), input_chars=unicode_len(TAG_BLOCK_62)
    )
    print(
        f"[F01] tag-block-62 fired={sorted(catalogue_numbers(findings))}",
        flush=True,
    )
    require_finding(findings, 62)
    assert 62 in catalogue_numbers(findings)


NONFIRE_CASES = [
    (
        "single-dialect",
        "That game-changer saved an afternoon on the lock.",
        (2,),
        "That genuinely fascinating trick is a game-changer that can supercharge the work.",
    ),
    (
        "noun-list",
        "We bought apples, oranges, bananas, grapes and pears for breakfast.",
        (6,),
        "They launched a bold, ambitious, transformative, innovative plan.",
    ),
    (
        "nanotech",
        "Our nanotechnology platform combines several proprietary techniques.",
        (8,),
        "The protagonist faces many challenges. The main character must overcome obstacles. "
        "The central figure eventually triumphs. The hero returns home.",
    ),
    (
        "from-9-to-5",
        "I worked from 9 to 5 yesterday, then went home.",
        (15,),
        "The story runs from the humble hand-forged nail to the mighty beam engine.",
    ),
    (
        "from-0-to-100",
        "Temperatures range from 0 to 100 degrees along the wall.",
        (15,),
        "The story runs from the humble hand-forged nail to the mighty beam engine.",
    ),
    (
        "boston-chicago",
        "We drove from Boston to Chicago, and the trip took three days.",
        (15,),
        "The story runs from the humble hand-forged nail to the mighty beam engine.",
    ),
    (
        "biology-chemistry",
        "The book covers everything from biology to chemistry, and reads well.",
        (15,),
        "The story runs from the humble hand-forged nail to the mighty beam engine.",
    ),
    (
        "ordinary-negation-teacher",
        "She is not a teacher, but a researcher on the lock survey.",
        (18,),
        "It's not just a hobby, it's a craft. No fluff, just results on the quay.",
    ),
    (
        "ordinary-negation-sleep",
        "I did not sleep well because of the noise from the weir.",
        (18,),
        "It's not just a hobby, it's a craft. No fluff, just results on the quay.",
    ),
    (
        "great-question-in",
        "The committee debated whether representation was a great question in the "
        "colonies, but the larger issue was taxation.",
        (47, 48),
        "Great question! I hope this helps with the draft today.",
    ),
    (
        "month-may",
        "In May 2025 the team shipped the lock repair on time.",
        (54,),
        HEDGE_STACK,
    ),
    (
        "utm-other-domain",
        f"Visit {TRACKING_OTHER_DOMAIN} for the AU site.",
        (65,),
        f"Full writeup at {TRACKING_URL} today.",
    ),
    (
        "genuine-cyrillic",
        "Москва is the capital of Russia.",
        (66,),
        "The p\u0430ssword field is wr\u043eng.",
    ),
    (
        "trailing-newline",
        "A single paragraph with a conventional trailing newline.\n",
        (68,),
        "Pasted text with stray trailing spaces.   ",
    ),
    (
        "single-however",
        "However you slice it the lock still opens at dawn.",
        (37,),
        "Additionally the wall held. Furthermore the pier held. Moreover the deck held.",
    ),
    (
        "native-mixed-name",
        "Pay СберBank today at the quay office.",
        (66,),
        "The p\u0430ssword field is wr\u043eng.",
    ),
    (
        "non-latin-url",
        "See москва.рф/index for the lock archive.",
        (66,),
        "The p\u0430ssword field is wr\u043eng.",
    ),
]


@pytest.mark.parametrize(
    "name,text,numbers,baseline",
    NONFIRE_CASES,
    ids=[c[0] for c in NONFIRE_CASES],
)
def test_constructable_non_fires_stay_quiet_with_live_baselines(
    name, text, numbers, baseline
):
    quiet_f, _ = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    live_f, _ = require_success_report(
        scan_stdin(baseline), input_chars=unicode_len(baseline)
    )
    print(f"[F01] non-fire {name}", flush=True)
    for number in numbers:
        require_absent_finding(quiet_f, number)
        require_finding(live_f, number)
        assert number not in catalogue_numbers(quiet_f)
        assert number in catalogue_numbers(live_f)


def test_great_question_chatbot_punctuation_is_sycophantic_not_chatbot():
    text = "Great question!"
    findings, _ = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 48)
    require_absent_finding(findings, 47)
    assert 48 in catalogue_numbers(findings)
    assert 47 not in catalogue_numbers(findings)


def test_nbsp_fires_nonstandard_spaces_not_invisible():
    text = "Two\u00a0words sit on the page near the lock."
    findings, _ = require_success_report(
        scan_stdin(text), input_chars=unicode_len(text)
    )
    require_finding(findings, 67)
    require_absent_finding(findings, 62)
    assert 67 in catalogue_numbers(findings)
    assert 62 not in catalogue_numbers(findings)


def test_nbsp_moves_nonstandard_space_count():
    # Same prose on both arms; only the second carries the no-break spaces.
    plain, nbsp = nonstandard_space_arms()
    p_f, p_m = require_success_report(
        scan_stdin(plain), input_chars=unicode_len(plain)
    )
    n_f, n_m = require_success_report(
        scan_stdin(nbsp), input_chars=unicode_len(nbsp)
    )
    require_finding(n_f, 67)
    require_absent_finding(n_f, 62)
    assert nonstandard_space_count_of(n_m) > nonstandard_space_count_of(p_m)
    assert 67 in catalogue_numbers(n_f)
    assert 62 not in catalogue_numbers(n_f)


def test_single_dialect_word_does_not_fire_model_dialect():
    one = "That game-changer saved an afternoon on the lock."
    two = (
        "That genuinely fascinating trick is a game-changer that can supercharge the work."
    )
    o_f, _ = require_success_report(scan_stdin(one), input_chars=unicode_len(one))
    t_f, _ = require_success_report(scan_stdin(two), input_chars=unicode_len(two))
    require_absent_finding(o_f, 2)
    require_finding(t_f, 2)
    assert 2 not in catalogue_numbers(o_f)
    assert 2 in catalogue_numbers(t_f)


# ===========================================================================
# K. BOM / CRLF / interior ZW
# ===========================================================================


def test_leading_utf8_bom_and_crlf_do_not_add_invisible_findings_or_mixed_band():
    human = SHORT_FACTUAL.replace(". ", ".\r\n")
    payload = b"\xef\xbb\xbf" + human.encode("utf-8")
    with workspace() as ws:
        ws.write("bom.md", payload)
        result = scan_path(ws, "bom.md")
    findings, metrics = require_success_report(result)
    require_absent_finding(findings, 62)
    score = score_of(metrics, findings=findings)
    assert score <= 40
    assert band_of(metrics) not in ("mixed", "heavy tells", "pervasive tells")
    # Live arm (L110): the same human prose with an interior zero-width
    # character does add an invisible-character finding. A detector that
    # never emits 62 cannot satisfy this contrast.
    zw = SHORT_FACTUAL[:40] + "\u200b" + SHORT_FACTUAL[40:]
    z_f, _z_m = require_success_report(
        scan_stdin(zw), input_chars=unicode_len(zw)
    )
    require_finding(z_f, 62)
    assert 62 in catalogue_numbers(z_f)
    assert 62 not in catalogue_numbers(findings)


def test_interior_zero_width_adds_invisible_character_finding():
    zw = SHORT_FACTUAL[:40] + "\u200b" + SHORT_FACTUAL[40:]
    findings, _ = require_success_report(
        scan_stdin(zw), input_chars=unicode_len(zw)
    )
    require_finding(findings, 62)
    assert 62 in catalogue_numbers(findings)


def test_interior_zero_width_moves_invisible_character_count():
    human = SHORT_FACTUAL.replace(". ", ".\r\n")
    bom = b"\xef\xbb\xbf" + human.encode("utf-8")
    plain, zw = zero_width_arms()
    with workspace() as ws:
        ws.write("bom.md", bom)
        bom_r = scan_path(ws, "bom.md")
    b_f, b_m = require_success_report(bom_r)
    p_f, p_m = require_success_report(
        scan_stdin(plain), input_chars=unicode_len(plain)
    )
    z_f, z_m = require_success_report(
        scan_stdin(zw), input_chars=unicode_len(zw)
    )
    require_absent_finding(b_f, 62)
    require_absent_finding(p_f, 62)
    require_finding(z_f, 62)
    assert invisible_count_of(z_m) > invisible_count_of(p_m)
    assert invisible_count_of(z_m) > invisible_count_of(b_m)


# ===========================================================================
# L. Interval switch
# ===========================================================================


def test_interval_switch_adds_low_high_without_replacing_point_score():
    flag = INTERVAL_FLAG
    four = (
        "The lock opened at dawn. Barges waited below the ridge. "
        "Crews cleared the silt. Stone from the quarry still faces west."
    )
    off = scan_stdin(four)
    on = scan_stdin(four, extra_args=(flag,))
    off_f, off_m = require_success_report(off, input_chars=unicode_len(four))
    on_f, on_m = require_success_report(on, input_chars=unicode_len(four))
    off_score = score_of(off_m, findings=off_f)
    on_score = score_of(on_m, findings=on_f)
    assert off_score == on_score
    assert INTERVAL_KEY not in off_m
    assert not interval_present(off_m, off_score)
    assert interval_present(on_m, on_score)
    # L111: a low/high interval ([low, high] under score_ci) is present and
    # does not replace the point score.
    assert isinstance(on_score, int) and 0 <= on_score <= 100
    print(f"[F01] interval present on >=4 sentences; score {on_score} unchanged", flush=True)


def test_interval_omitted_when_fewer_than_four_sentences():
    flag = INTERVAL_FLAG
    two = "The lock opened at dawn. Barges waited below the ridge."
    four = (
        "The lock opened at dawn. Barges waited below the ridge. "
        "Crews cleared the silt. Stone from the quarry still faces west."
    )
    two_on = scan_stdin(two, extra_args=(flag,))
    four_on = scan_stdin(four, extra_args=(flag,))
    four_off = scan_stdin(four)
    t_f, t_m = require_success_report(two_on, input_chars=unicode_len(two))
    f_f, f_m = require_success_report(four_on, input_chars=unicode_len(four))
    _off_f, off_m = require_success_report(four_off, input_chars=unicode_len(four))
    t_score = score_of(t_m, findings=t_f)
    f_score = score_of(f_m, findings=f_f)
    off_score = score_of(off_m, findings=_off_f)
    assert not interval_present(t_m, t_score)
    assert interval_present(f_m, f_score)
    assert not interval_present(off_m, off_score)
    assert INTERVAL_KEY not in off_m
    # Point score still present on the omitted-interval arm (L111).
    assert isinstance(t_score, int) and 0 <= t_score <= 100
    # L111: on the omitted-interval arm, metrics state there are too few
    # sentences: score_ci is null (score_ci_note is free text).
    too_few_sentences_stated(t_m)
    assert f_score == off_score


# ===========================================================================
# M. Help, usage, double-dash
# ===========================================================================


def test_help_request_from_usage_prints_usage_and_succeeds():
    # The help switch and its short alias print the usage message on
    # standard output and succeed; the usage's first line is the stated
    # synopsis.
    for token in (HELP_FLAG, HELP_SHORT):
        result = invoke([token])
        print(f"[F01] help token {token!r} exit={result.returncode}", flush=True)
        assert result.returncode == 0, (
            f"{token} exited {result.returncode}; stderr={result.stderr_text[:300]!r}"
        )
        assert result.stdout.strip(), f"{token} printed nothing on standard output"
        require_usage_message(result.stdout_text)


def test_usage_names_cleanup_interval_double_dash_and_file_operand():
    # Usage names the cleanup switch, the interval switch, the double-dash,
    # and the single-file operand: the stated synopsis line carries all four.
    usage = usage_from_help()
    first = usage.splitlines()[0]
    assert first == USAGE_SYNOPSIS
    tokens = first.replace("[", " ").replace("]", " ").split()
    for needed in ("--clean", INTERVAL_FLAG, "--", "FILE"):
        assert needed in tokens, f"usage synopsis does not name {needed!r}"


def test_double_dash_then_dash_filename_scans():
    body = SHORT_FACTUAL
    with workspace() as ws:
        ws.write("-notes.txt", body)
        ws.write("notes.txt", body)
        # L91: the argv operand itself begins with a dash. An absolute
        # resolved path would not start with '-', so -- would not be
        # what made the scan succeed.
        dashed = ws.invoke(["--", "-notes.txt"])
        plain = scan_path(ws, "notes.txt")
    d_f, d_m = require_success_report(dashed, input_chars=unicode_len(body))
    p_f, p_m = require_success_report(plain, input_chars=unicode_len(body))
    assert dashed.returncode == 0
    assert score_of(d_m, findings=d_f) == score_of(p_m, findings=p_f)
    assert catalogue_numbers(d_f) == catalogue_numbers(p_f)


# ===========================================================================
# N. Empty extracted prose
# ===========================================================================


def test_empty_stdin_fails_structured_and_without_traceback():
    empty = scan_stdin("")
    err = require_structured_failure(empty)
    unknown_tok = "--zz" + "q9x"
    unknown = scan_stdin(SHORT_FACTUAL, extra_args=(unknown_tok,))
    uerr = require_structured_failure(unknown)
    assert empty.returncode != 0
    assert unknown.returncode != 0
    assert empty.returncode != unknown.returncode
    stripped_empty = strip_error_covariates(err, unknown_tok)
    stripped_unknown = strip_error_covariates(uerr, unknown_tok)
    assert stripped_empty
    assert stripped_empty != stripped_unknown
    assert unknown_tok in uerr
    assert err == EMPTY_INPUT_ERROR
    assert empty.returncode == EXIT_EMPTY_INPUT
    assert unknown.returncode == EXIT_UNKNOWN_OPTION
    with workspace() as ws:
        missing = str(ws.resolve("missing.txt"))
        unread = ws.invoke([missing])
        uerr_unread = require_structured_failure(unread)
        stripped_unread = strip_error_covariates(
            strip_paths_from_stderr(uerr_unread, missing), missing
        )
        ws.write("notzip.docx", b"this is not a zip archive at all")
        path_bad = str(ws.resolve("notzip.docx"))
        bad = scan_path(ws, "notzip.docx")
        bad_err = require_structured_failure(bad)
        stripped_bad = strip_error_covariates(
            strip_paths_from_stderr(bad_err, path_bad), path_bad
        )
    # L115–L116 / L126: unreadable and non-zip share empty-input's failing
    # status family (not the unknown-option status) but a different kind.
    assert unread.returncode != 0
    assert bad.returncode != 0
    assert unread.returncode != unknown.returncode
    assert bad.returncode != unknown.returncode
    assert unread.returncode == empty.returncode
    assert bad.returncode == empty.returncode
    assert unread.returncode == EXIT_UNREADABLE
    assert bad.returncode == EXIT_UNREADABLE
    assert is_unreadable_error(uerr_unread)
    assert is_unreadable_error(bad_err)
    assert stripped_empty != stripped_unread
    assert stripped_empty != stripped_bad
    empty_input_identity(
        [stripped_empty], [stripped_unknown, stripped_unread, stripped_bad]
    )


def test_empty_file_notebook_archive_pdf_rtf_fail_as_empty_extracted_prose():
    unknown_tok = "--zz" + "k3w"
    unknown = scan_stdin(SHORT_FACTUAL, extra_args=(unknown_tok,))
    uerr = require_structured_failure(unknown)
    empty_stdin = scan_stdin("")
    prose_cell = "The lock opened at dawn after the spring flood receded."
    with workspace() as ws:
        ws.write("empty.txt", "")
        nb = json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "source": [prose_cell + "\n"],
                        "metadata": {},
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 2,
            }
        )
        ws.write("only_code.ipynb", nb)
        empty_zip = ws.resolve("empty.docx")
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("readme.txt", "")
        ws.write("blank.pdf", b"%PDF-1.4 empty")
        ws.write("blank.rtf", b"{\\rtf1 empty}")
        path_empty = str(ws.resolve("empty.txt"))
        path_nb = str(ws.resolve("only_code.ipynb"))
        path_zip = str(empty_zip)
        path_pdf = str(ws.resolve("blank.pdf"))
        path_rtf = str(ws.resolve("blank.rtf"))
        missing = str(ws.resolve("missing.txt"))
        unread = ws.invoke([missing])
        arms = [
            (empty_stdin, ()),
            (scan_path(ws, "empty.txt"), (path_empty,)),
            (scan_path(ws, "only_code.ipynb"), (path_nb,)),
            (scan_path(ws, "empty.docx"), (path_zip,)),
            (scan_path(ws, "blank.pdf"), (path_pdf,)),
            (scan_path(ws, "blank.rtf"), (path_rtf,)),
        ]
        unread_err = require_structured_failure(unread)
        unread_kind = strip_error_covariates(
            strip_paths_from_stderr(unread_err, missing), unknown_tok, missing
        )
        ws.write("notzip.docx", b"this is not a zip archive at all")
        path_bad = str(ws.resolve("notzip.docx"))
        bad = scan_path(ws, "notzip.docx")
        bad_err = require_structured_failure(bad)
        bad_kind = strip_error_covariates(
            strip_paths_from_stderr(bad_err, path_bad), unknown_tok, path_bad
        )
    kinds = []
    statuses = []
    for result, paths in arms:
        err = require_structured_failure(result)
        stripped = strip_error_covariates(
            strip_paths_from_stderr(err, *paths), unknown_tok, *paths
        )
        kinds.append(stripped)
        statuses.append(result.returncode)
        assert result.returncode != 0
        assert result.returncode == EXIT_EMPTY_INPUT
        assert result.returncode != unknown.returncode
        assert err == EMPTY_INPUT_ERROR
        assert stripped != strip_error_covariates(uerr, unknown_tok)
    assert len(set(kinds)) == 1
    assert len(set(statuses)) == 1
    # L116: unreadable / non-zip share that status family, not the kind.
    assert unread.returncode == statuses[0]
    assert bad.returncode == statuses[0]
    assert unread.returncode != unknown.returncode
    assert bad.returncode != unknown.returncode
    assert kinds[0] != unread_kind
    assert kinds[0] != bad_kind
    assert is_unreadable_error(unread_err)
    assert is_unreadable_error(bad_err)
    empty_input_identity(
        kinds,
        [strip_error_covariates(uerr, unknown_tok), unread_kind, bad_kind],
    )


# ===========================================================================
# O. Unreadable path / non-zip archive
# ===========================================================================


def test_unreadable_path_fails_structured_without_traceback():
    with workspace() as ws:
        result = ws.invoke([str(ws.resolve("missing.txt"))])
    err = require_structured_failure(result)
    mapping = structured_error_mapping(result)
    assert mapping
    assert err
    assert result.returncode == EXIT_UNREADABLE
    assert is_unreadable_error(err)
    assert err != EMPTY_INPUT_ERROR


def test_supported_archive_extension_that_is_not_a_zip_fails_structured_without_traceback():
    with workspace() as ws:
        ws.write("fake.docx", b"this is not a zip archive at all")
        result = scan_path(ws, "fake.docx")
    err = require_structured_failure(result)
    mapping = structured_error_mapping(result)
    assert mapping
    assert err
    assert result.returncode == EXIT_UNREADABLE
    assert is_unreadable_error(err)
    assert err != EMPTY_INPUT_ERROR


# ===========================================================================
# P. Unknown option
# ===========================================================================


def test_unknown_option_fails_distinctly_from_empty_input():
    token = "--zz" + "u7m"
    empty = scan_stdin("")
    unknown = scan_stdin(SHORT_FACTUAL, extra_args=(token,))
    eerr = require_structured_failure(empty)
    uerr = require_structured_failure(unknown)
    assert empty.returncode != unknown.returncode
    assert empty.returncode == EXIT_EMPTY_INPUT
    assert unknown.returncode == EXIT_UNKNOWN_OPTION
    assert eerr == EMPTY_INPUT_ERROR
    assert token in uerr
    assert UNKNOWN_OPTION_WORDS in uerr
    assert strip_error_covariates(eerr, token) != strip_error_covariates(uerr, token)
    error_points_toward_help(uerr)


# ===========================================================================
# Q. Extra file operands
# ===========================================================================


def test_two_file_operands_scan_the_first_and_warn_on_stderr():
    with workspace() as ws:
        ws.write("first.txt", SHORT_FACTUAL)
        ws.write("second.txt", SHORT_SLOP)
        first_path = str(ws.resolve("first.txt"))
        second_path = str(ws.resolve("second.txt"))
        multi = ws.invoke([first_path, second_path])
        single = ws.invoke([first_path])
        only_second = ws.invoke([second_path])
    m_f, m_m = require_success_report(multi, input_chars=unicode_len(SHORT_FACTUAL))
    s_f, s_m = require_success_report(single, input_chars=unicode_len(SHORT_FACTUAL))
    o_f, o_m = require_success_report(only_second, input_chars=unicode_len(SHORT_SLOP))
    assert score_of(m_m, findings=m_f) == score_of(s_m, findings=s_f)
    assert catalogue_numbers(m_f) == catalogue_numbers(s_f)
    assert score_of(m_m, findings=m_f) != score_of(o_m, findings=o_f)
    require_no_traceback(multi)
    # Contract: a non-JSON stderr notice line names the scanned (first)
    # operand as given; a single operand prints no such line.
    stderr_states_one_file_at_a_time(multi.stderr_text, first_path)
    assert not multi_file_notice_lines(single.stderr_text, first_path)
    print(f"[F01] extra-operand stderr={multi.stderr_text!r}", flush=True)


def test_extra_operands_are_not_dropped_silently():
    with workspace() as ws:
        ws.write("a.txt", SHORT_FACTUAL)
        ws.write("b.txt", SHORT_SLOP)
        ws.write("c.txt", HUMANIZED_CODING)
        a = str(ws.resolve("a.txt"))
        b = str(ws.resolve("b.txt"))
        c = str(ws.resolve("c.txt"))
        three = ws.invoke([a, b, c])
        one = ws.invoke([a])
    t_f, t_m = require_success_report(three, input_chars=unicode_len(SHORT_FACTUAL))
    o_f, o_m = require_success_report(one, input_chars=unicode_len(SHORT_FACTUAL))
    assert score_of(t_m, findings=t_f) == score_of(o_m, findings=o_f)
    assert catalogue_numbers(t_f) == catalogue_numbers(o_f)
    require_no_traceback(three)
    stderr_states_one_file_at_a_time(three.stderr_text, a)
    assert not multi_file_notice_lines(one.stderr_text, a)


# ===========================================================================
# R. 262,144-character window
# ===========================================================================


def test_at_cap_file_is_not_truncated():
    body = padding_of_length(SCAN_CAP)
    over = padding_of_length(SCAN_CAP + 1)
    extra = padding_of_length(SCAN_CAP + 2)
    with workspace() as ws:
        ws.write("at.txt", body)
        ws.write("over.txt", over)
        ws.write("extra.txt", extra)
        at_r = scan_path(ws, "at.txt")
        over_r = scan_path(ws, "over.txt")
        extra_r = scan_path(ws, "extra.txt")
    at_f, at_m = require_success_report(at_r, input_chars=SCAN_CAP)
    over_f, over_m = require_success_report(over_r, input_chars=SCAN_CAP + 1)
    _ef, extra_m = require_success_report(extra_r, input_chars=SCAN_CAP + 2)
    short_r = scan_stdin(SHORT_FACTUAL)
    _sf, short_m = require_success_report(
        short_r, input_chars=unicode_len(SHORT_FACTUAL)
    )
    assert scanned_of(at_m, chars=SCAN_CAP) == SCAN_CAP
    assert scanned_of(over_m, chars=SCAN_CAP + 1) == SCAN_CAP
    assert scanned_of(extra_m, chars=SCAN_CAP + 2) == SCAN_CAP
    # Two-valued longer-than-window indication: _metrics.truncated is
    # false at the cap and true one or two characters past it.
    at_mark = window_mark_of(at_m)
    over_mark = window_mark_of(over_m)
    extra_mark = window_mark_of(extra_m)
    short_mark = window_mark_of(short_m)
    assert at_mark != over_mark
    assert extra_mark == over_mark
    assert short_mark == at_mark
    assert window_is_not_longer(at_m), (
        "at-cap report must carry the not-longer value of the two-valued "
        "longer-than-window indication"
    )
    assert window_is_longer(over_m), (
        "over-window report must carry the longer value of the two-valued "
        "longer-than-window indication"
    )
    assert window_is_longer(extra_m)
    assert window_is_not_longer(short_m)
    assert at_m[TRUNCATED_KEY] is False and over_m[TRUNCATED_KEY] is True
    print("[F01] at-cap not-longer; over-window longer (two-valued)", flush=True)


def test_one_past_cap_marks_truncated_and_reports_262144_scanned():
    body = padding_of_length(SCAN_CAP + 1)
    extra = padding_of_length(SCAN_CAP + 2)
    cap_body = padding_of_length(SCAN_CAP)
    with workspace() as ws:
        ws.write("over.txt", body)
        ws.write("extra.txt", extra)
        ws.write("at.txt", cap_body)
        result = scan_path(ws, "over.txt")
        extra_r = scan_path(ws, "extra.txt")
        at_r = scan_path(ws, "at.txt")
    _findings, metrics = require_success_report(result, input_chars=SCAN_CAP + 1)
    _ef, extra_m = require_success_report(extra_r, input_chars=SCAN_CAP + 2)
    _af, at_m = require_success_report(at_r, input_chars=SCAN_CAP)
    assert scanned_of(metrics, chars=SCAN_CAP + 1) == SCAN_CAP
    assert scanned_of(at_m, chars=SCAN_CAP) == SCAN_CAP
    short_r = scan_stdin(SHORT_FACTUAL)
    _sf, short_m = require_success_report(
        short_r, input_chars=unicode_len(SHORT_FACTUAL)
    )
    at_mark = window_mark_of(at_m)
    over_mark = window_mark_of(metrics)
    extra_mark = window_mark_of(extra_m)
    assert over_mark != at_mark
    assert extra_mark == over_mark
    assert window_is_longer(metrics), (
        "over-window report must carry the longer value of the two-valued "
        "longer-than-window indication"
    )
    assert window_is_not_longer(at_m), (
        "at-cap report must carry the not-longer value of the two-valued "
        "longer-than-window indication"
    )
    assert window_is_longer(extra_m)
    print("[F01] one-past longer; at-cap not-longer; scanned 262144", flush=True)


def test_character_layer_findings_ignore_bytes_past_the_window():
    hom = "p\u0430ssword"
    prefix = padding_of_length(SCAN_CAP)
    past = prefix + hom
    inside = hom + " " + padding_of_length(SCAN_CAP - len(hom) - 1)
    with workspace() as ws:
        ws.write("past.txt", past)
        ws.write("inside.txt", inside)
        past_r = scan_path(ws, "past.txt")
        inside_r = scan_path(ws, "inside.txt")
    p_f, _ = require_success_report(past_r, input_chars=unicode_len(past))
    i_f, _ = require_success_report(inside_r, input_chars=unicode_len(inside))
    require_absent_finding(p_f, 66)
    require_finding(i_f, 66)
    assert 66 not in catalogue_numbers(p_f)
    assert 66 in catalogue_numbers(i_f)

    zw = "\u200b"
    past_zw = prefix + zw
    inside_zw = "hi" + zw + "dden " + padding_of_length(SCAN_CAP - 8)
    with workspace() as ws:
        ws.write("past_zw.txt", past_zw)
        ws.write("inside_zw.txt", inside_zw)
        past_zw_r = scan_path(ws, "past_zw.txt")
        inside_zw_r = scan_path(ws, "inside_zw.txt")
    pz_f, _ = require_success_report(past_zw_r, input_chars=unicode_len(past_zw))
    iz_f, _ = require_success_report(inside_zw_r, input_chars=unicode_len(inside_zw))
    require_absent_finding(pz_f, 62)
    require_finding(iz_f, 62)
    assert 62 not in catalogue_numbers(pz_f)
    assert 62 in catalogue_numbers(iz_f)


# ===========================================================================
# S. NUL vs UTF-16
# ===========================================================================


def test_nul_without_utf16_bom_is_empty_input_failure():
    payload = b"The lock was rebuilt in 1804.\x00more"
    empty = scan_stdin("")
    eerr = require_structured_failure(empty)
    unknown_tok = "--zz" + "n0l"
    unknown = scan_stdin(SHORT_FACTUAL, extra_args=(unknown_tok,))
    uerr = require_structured_failure(unknown)
    with workspace() as ws:
        ws.write("nul.bin", payload)
        path = str(ws.resolve("nul.bin"))
        result = scan_path(ws, "nul.bin")
        missing = str(ws.resolve("missing.txt"))
        unread = ws.invoke([missing])
    nerr = require_structured_failure(result)
    uerr_unread = require_structured_failure(unread)
    stripped_empty = strip_error_covariates(eerr, unknown_tok, path)
    stripped_nul = strip_error_covariates(
        strip_paths_from_stderr(nerr, path), unknown_tok, path
    )
    stripped_unknown = strip_error_covariates(uerr, unknown_tok)
    stripped_unread = strip_error_covariates(
        strip_paths_from_stderr(uerr_unread, missing), missing
    )
    # L121: a NUL non-text buffer yields empty-input failure, not a
    # successful findings report of invented invisible-character hits.
    # UTF-16-with-BOM is the contrasting decoded-as-text arm, not this failure.
    assert result.returncode != 0
    assert empty.returncode != 0
    assert result.returncode == empty.returncode
    assert result.returncode != unknown.returncode
    assert unread.returncode == empty.returncode
    assert unread.returncode != unknown.returncode
    assert stripped_empty == stripped_nul
    assert nerr == EMPTY_INPUT_ERROR
    assert result.returncode == EXIT_EMPTY_INPUT
    assert stripped_nul != stripped_unknown
    assert stripped_nul != stripped_unread
    empty_input_identity(
        [stripped_empty, stripped_nul], [stripped_unknown, stripped_unread]
    )


def test_utf16_with_bom_is_decoded_as_text():
    twin = runtime_twin("factual")
    payload = twin.encode("utf-16")  # UTF-16 with a byte-order mark
    with workspace() as ws:
        ws.write("wide.txt", payload)
        result = scan_path(ws, "wide.txt")
    findings, metrics = require_success_report(result)
    assert score_of(metrics, findings=findings) <= 40
    assert band_of(metrics) in ("clean", "light tells")


# ===========================================================================
# T. UTF-8 stdin
# ===========================================================================


def test_utf8_stdin_scans_the_unicode_characters():
    text = "The café by the lock opened at dawn."
    twin = runtime_twin("cafe")
    for body in (text, twin):
        result = scan_stdin(body)
        decoded = require_stdout_utf8(result)
        _findings, metrics = require_success_report(
            result, input_chars=unicode_len(body)
        )
        assert scanned_of(metrics, chars=unicode_len(body)) == unicode_len(body)
        print(
            f"[F01] utf8 scanned={scanned_of(metrics)} chars={unicode_len(body)} "
            f"bytes={len(body.encode('utf-8'))} stdout_utf8={len(decoded)}",
            flush=True,
        )
        assert scanned_of(metrics) != len(body.encode("utf-8"))


# ===========================================================================
# U. Determinism
# ===========================================================================


def test_default_scan_is_deterministic():
    a = scan_stdin(SHORT_SLOP)
    b = scan_stdin(SHORT_SLOP)
    af, am = require_success_report(a, input_chars=unicode_len(SHORT_SLOP))
    bf, bm = require_success_report(b, input_chars=unicode_len(SHORT_SLOP))
    # L61: same extracted prose on the same detector produces the same
    # report. There is no model and no random component in the default scan.
    assert a.returncode == 0
    assert b.returncode == 0
    assert a.stdout == b.stdout
    assert score_of(am, findings=af) == score_of(bm, findings=bf)
    assert band_of(am) == band_of(bm)
    assert confidence_of(am) == confidence_of(bm)
    assert catalogue_numbers(af) == catalogue_numbers(bf)
    flag = INTERVAL_FLAG
    on = scan_stdin(SHORT_SLOP, extra_args=(flag,))
    on_f, on_m = require_success_report(on, input_chars=unicode_len(SHORT_SLOP))
    assert score_of(am, findings=af) == score_of(on_m, findings=on_f)


# ===========================================================================
# V. No network client
# ===========================================================================


def test_detector_scan_opens_no_connection_to_a_proxy_sink():
    with workspace() as ws:
        with proxy_sink() as sink:
            before = sink.n_connections
            result = ws.invoke(
                [],
                stdin=SHORT_FACTUAL,
                env_updates={
                    "HTTP_PROXY": sink.url,
                    "HTTPS_PROXY": sink.url,
                    "ALL_PROXY": sink.url,
                    "http_proxy": sink.url,
                    "https_proxy": sink.url,
                    "all_proxy": sink.url,
                },
            )
            require_success_report(result, input_chars=unicode_len(SHORT_FACTUAL))
            after = sink.n_connections
            print(
                f"[F01] proxy connects during scan: {after - before}",
                flush=True,
            )
            assert after == before
            sink.fire_positive_control()
            assert sink.n_connections > after
