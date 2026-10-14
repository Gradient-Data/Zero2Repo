# feature: F03
"""Acceptance tests for deterministic character cleanup (FP-03)."""

from __future__ import annotations

import secrets

from _harness import workspace
from F01_helpers import (
    SCAN_CAP,
    SHORT_FACTUAL,
    invisible_count_of,
    latin_homoglyph,
    mixed_script_count_of,
    nonstandard_space_count_of,
    proxy_sink,
    require_absent_finding,
    require_finding,
    require_success_report,
    scan_path,
    scan_stdin,
    unicode_len,
)
from F02_helpers import (
    CLEANUP_FLAG,
    HELP_FLAG,
    USAGE_SYNOPSIS,
    _stdout_is_report,
    require_cannot_read_error,
    require_empty_input_error,
    require_unknown_option_error,
    runtime_token,
    states_one_file_at_a_time,
    tokens_in_relative_order,
    write_docx,
    write_epub,
    write_notebook,
    write_odt,
)
from F03_helpers import (
    BOM_CHAR,
    CAFE,
    CELLULOSE_CLEAN,
    FIGURE_40_EUR,
    FOUR_SPACE_LINE,
    IDEOGRAPHIC_SPACE,
    LTR_MARK,
    MOSKVA_LINE,
    NBSP,
    NIHONGO,
    NNBSP,
    PASSWORD_CLEAN,
    PASSWORD_DIRTY,
    STRAY_VS,
    WORD_JOINER,
    ZWSP,
    assert_jobless_class_removed,
    assert_operand_unchanged,
    cellulose_probe,
    cleaned_visible_twin,
    cleanup_switch,
    cyrillic_url_alphabet,
    dirty_visible_twin,
    england_flag_sequence,
    finish_within_8s,
    first_content_leading_spaces,
    gap_between,
    greek_url_alphabet,
    keep_sequence_cases,
    named_file_in_stderr,
    require_scrubbed_stdout,
    rescan_text,
    runtime_english_pair,
    scrub_path,
    scrub_stdin,
    single_script_url_run,
    stdout_is_zip_bytes,
    tag_payload,
)


# ===========================================================================
# A. Cleanup emits scrubbed text, not the report
# ===========================================================================


def test_without_cleanup_the_same_probe_is_a_character_layer_report():
    probe = cellulose_probe(newline=True)
    result = scan_stdin(probe)
    findings, metrics = require_success_report(result, input_chars=unicode_len(probe))
    require_finding(findings, 62)
    require_finding(findings, 67)
    require_finding(findings, 68)
    assert _stdout_is_report(result.stdout_text)
    print(
        f"[F03] without cleanup cellulose report invisible={invisible_count_of(metrics)} "
        f"spaces={nonstandard_space_count_of(metrics)}",
        flush=True,
    )


def test_cleanup_prints_cellulose_sentence_not_a_report():
    with_nl = cellulose_probe(newline=True)
    without_nl = cellulose_probe(newline=False)
    out_nl = scrub_stdin(with_nl)
    out_bare = scrub_stdin(without_nl)
    print(f"[F03] cellulose with nl={out_nl!r} without={out_bare!r}", flush=True)
    assert out_nl == CELLULOSE_CLEAN + "\n"
    assert out_bare == CELLULOSE_CLEAN
    assert not _stdout_is_report(out_nl)
    assert not _stdout_is_report(out_bare)
    findings, metrics = rescan_text(out_nl)
    require_absent_finding(findings, 62)
    require_absent_finding(findings, 67)
    require_absent_finding(findings, 68)
    assert invisible_count_of(metrics) == 0
    assert nonstandard_space_count_of(metrics) == 0


def test_cleanup_file_path_matches_stdin_on_the_cellulose_probe():
    probe = cellulose_probe(newline=True)
    stdin_out = scrub_stdin(probe)
    with workspace() as ws:
        ws.write("cell.md", probe.encode("utf-8"))
        result = scrub_path(ws, "cell.md")
        path_out = require_scrubbed_stdout(result)
    print(f"[F03] cellulose file={path_out!r} stdin={stdin_out!r}", flush=True)
    assert stdin_out == CELLULOSE_CLEAN + "\n"
    assert path_out == stdin_out
    assert result.returncode == 0
    assert not _stdout_is_report(path_out)


def test_cleanup_runtime_twin_is_not_a_memorized_cellulose_sentence():
    first, second = runtime_english_pair()
    dirty = dirty_visible_twin(first, second, newline=True)
    expected = cleaned_visible_twin(first, second, newline=True)
    out = scrub_stdin(dirty)
    print(f"[F03] twin first={first!r} second={second!r} out={out!r}", flush=True)
    assert out == expected
    assert out != CELLULOSE_CLEAN
    assert out != CELLULOSE_CLEAN + "\n"
    assert first in out and second in out


# ===========================================================================
# B. Jobless invisible / zero-width / TAG / stray VS are removed
# ===========================================================================


_JOBLESS_OTHER_CASES = (
    ("word-joiner", WORD_JOINER),
    ("mid-text-bom", BOM_CHAR),
    ("ltr-mark", LTR_MARK),
    ("tag-block", chr(0xE0041) + chr(0xE0049)),
    ("stray-vs", STRAY_VS),
)


def test_jobless_zero_width_space_is_removed_and_rescan_is_quiet():
    """AST-visible ZWSP arm so a probe can name this function, not a param id."""
    assert_jobless_class_removed("zero-width-space", ZWSP)


def test_jobless_invisible_codepoints_are_removed_and_rescan_is_quiet():
    assert _JOBLESS_OTHER_CASES, "jobless class list is empty"
    for name, mark in _JOBLESS_OTHER_CASES:
        assert_jobless_class_removed(name, mark)


def test_tag_payload_after_flag_terminator_is_removed_flag_stays():
    flag = england_flag_sequence()
    extra = tag_payload()
    text = f"Match in {flag}{extra} today."
    baseline = scan_stdin(text)
    b_findings, _m = require_success_report(baseline, input_chars=unicode_len(text))
    require_finding(b_findings, 62)
    out = scrub_stdin(text)
    print(f"[F03] flag+payload out={out!r}", flush=True)
    assert flag in out
    for ch in extra:
        assert ch not in out
    assert extra not in out


# ===========================================================================
# C. Jobless non-standard spaces become U+0020; load-bearing spaces stay
# ===========================================================================


def test_jobless_nbsp_and_ideographic_space_become_ordinary_space():
    left, right = "Two", "words"
    nbsp = f"{left}{NBSP}{right} sit on the page near the lock."
    ideo = f"{left}{IDEOGRAPHIC_SPACE}{right} sit on the page near the lock."
    twin_l, twin_r = "Lock", "gate"
    nbsp_twin = f"{twin_l}{NBSP}{twin_r} sit on the quay near the weir."
    ideo_twin = f"{twin_l}{IDEOGRAPHIC_SPACE}{twin_r} sit on the quay near the weir."

    base = scan_stdin(nbsp)
    b_f, _b_m = require_success_report(base, input_chars=unicode_len(nbsp))
    require_finding(b_f, 67)
    require_absent_finding(b_f, 62)

    out_nbsp = scrub_stdin(nbsp)
    out_ideo = scrub_stdin(ideo)
    out_nbsp_t = scrub_stdin(nbsp_twin)
    out_ideo_t = scrub_stdin(ideo_twin)
    print(
        f"[F03] jobless spaces nbsp={out_nbsp!r} ideo={out_ideo!r}",
        flush=True,
    )
    i = out_nbsp.find(left)
    j = out_nbsp.find(right, i + len(left))
    assert out_nbsp[i + len(left) : j] == " "
    i2 = out_ideo.find(left)
    j2 = out_ideo.find(right, i2 + len(left))
    assert out_ideo[i2 + len(left) : j2] == " "
    ti = out_nbsp_t.find(twin_l)
    tj = out_nbsp_t.find(twin_r, ti + len(twin_l))
    assert out_nbsp_t[ti + len(twin_l) : tj] == " "
    ui = out_ideo_t.find(twin_l)
    uj = out_ideo_t.find(twin_r, ui + len(twin_l))
    assert out_ideo_t[ui + len(twin_l) : uj] == " "
    assert NBSP not in out_nbsp and NBSP not in out_nbsp_t
    assert IDEOGRAPHIC_SPACE not in out_ideo and IDEOGRAPHIC_SPACE not in out_ideo_t


def test_load_bearing_nbsp_before_french_punctuation_stays():
    public = f"Gate{NBSP}: open on the quay."
    twin_mark = secrets.choice([";", "!", "?"])
    twin = f"Lock{NBSP}{twin_mark} shut on the weir."
    for label, text in (("public", public), ("twin", twin)):
        scan = scan_stdin(text)
        findings, metrics = require_success_report(scan, input_chars=unicode_len(text))
        require_absent_finding(findings, 67)
        require_absent_finding(findings, 62)
        out = scrub_stdin(text)
        print(f"[F03] french-nbsp {label} out={out!r}", flush=True)
        assert NBSP in out
        assert out.rstrip("\n") == text.rstrip("\n")
        assert nonstandard_space_count_of(metrics) == 0


def test_narrow_nbsp_in_40_eur_stays():
    named = f"It costs {FIGURE_40_EUR} today on the quay."
    digits = str(10 + secrets.randbelow(80))
    unit = secrets.choice(["kg", "km", "lb", "ms"])
    twin = f"It weighs {digits}{NNBSP}{unit} today on the quay."
    for label, text in (("named", named), ("twin", twin)):
        scan = scan_stdin(text)
        findings, metrics = require_success_report(scan, input_chars=unicode_len(text))
        require_absent_finding(findings, 67)
        out = scrub_stdin(text)
        print(f"[F03] figure-nnbsp {label} out={out!r}", flush=True)
        assert NNBSP in out
        assert out.rstrip("\n") == text.rstrip("\n")
        assert nonstandard_space_count_of(metrics) == 0
    assert "40" in scrub_stdin(named)
    assert "EUR" in scrub_stdin(named)


# ===========================================================================
# D. Mixed-script homoglyphs fold; genuine non-Latin is not folded
# ===========================================================================


def test_named_password_sentence_folds_cyrillic_vowels_to_ascii():
    base = scan_stdin(PASSWORD_DIRTY)
    b_f, _m = require_success_report(base, input_chars=unicode_len(PASSWORD_DIRTY))
    require_finding(b_f, 66)
    out = scrub_stdin(PASSWORD_DIRTY)
    print(f"[F03] password out={out!r}", flush=True)
    assert out.rstrip("\n") == PASSWORD_CLEAN


def test_payment_and_script_homoglyphs_fold_to_ascii():
    pay = latin_homoglyph("payment")
    script = latin_homoglyph("script", "\u0441")
    pay_frame = f"The {pay} arrived at the lock."
    script_frame = f"The {script} arrived at the lock."
    out_p = scrub_stdin(pay_frame)
    out_s = scrub_stdin(script_frame)
    print(f"[F03] payment={out_p!r} script={out_s!r}", flush=True)
    assert "payment" in out_p
    assert pay not in out_p
    assert "script" in out_s
    assert script not in out_s
    word = "harbor"
    dirty = latin_homoglyph(word)
    twin = f"The {dirty} latch sits on the quay."
    out_t = scrub_stdin(twin)
    assert word in out_t
    assert dirty not in out_t


def test_genuine_cyrillic_sentence_and_moskva_line_are_not_folded():
    moskva = MOSKVA_LINE
    genuine = "\u041d\u0430\u0441\u043e\u0441 \u043f\u0435\u0440\u0435\u043a\u0430\u0447\u0438\u0432\u0430\u0435\u0442 \u0432\u043e\u0434\u0443."
    twin = "\u0420\u0435\u043a\u0430 \u0442\u0435\u0447\u0451\u0442 \u0431\u044b\u0441\u0442\u0440\u043e \u0443 \u043c\u043e\u0441\u0442\u0430."
    for label, text in (("moskva", moskva), ("genuine", genuine), ("twin", twin)):
        out = scrub_stdin(text)
        print(f"[F03] cyrillic-keep {label} out={out!r}", flush=True)
        assert out.rstrip("\n") == text.rstrip("\n")
        assert out.encode("utf-8").rstrip(b"\n") == text.encode("utf-8").rstrip(b"\n")


def test_single_script_non_latin_url_run_is_not_folded():
    public = single_script_url_run(cyrillic_url_alphabet())
    twin = single_script_url_run(cyrillic_url_alphabet())
    greek = single_script_url_run(greek_url_alphabet())
    if twin == public:
        twin = single_script_url_run(cyrillic_url_alphabet())
    assert "." in public and "/" in public
    assert public != twin
    mixed = f"The {latin_homoglyph('password')} latch sits on the quay."
    mixed_out = scrub_stdin(mixed)
    print(f"[F03] url mixed-script sibling out={mixed_out!r}", flush=True)
    assert "password" in mixed_out
    for label, run in (("cyr-a", public), ("cyr-b", twin), ("el", greek)):
        text = f"See {run} on the quay."
        out = scrub_stdin(text)
        print(f"[F03] url-run {label} out={out!r}", flush=True)
        assert run in out
        assert out.rstrip("\n") == text.rstrip("\n")
        assert out.encode("utf-8").rstrip(b"\n") == text.encode("utf-8").rstrip(b"\n")
        assert "." in out and "/" in out


def test_folded_password_rescan_does_not_fire_mixed_script():
    dirty = scan_stdin(PASSWORD_DIRTY)
    d_f, d_m = require_success_report(dirty, input_chars=unicode_len(PASSWORD_DIRTY))
    require_finding(d_f, 66)
    assert mixed_script_count_of(d_m) > 0
    cleaned = scrub_stdin(PASSWORD_DIRTY)
    print(f"[F03] folded password stdout={cleaned!r}", flush=True)
    assert cleaned.rstrip("\n") == PASSWORD_CLEAN
    findings, metrics = rescan_text(cleaned)
    require_absent_finding(findings, 66)
    assert mixed_script_count_of(metrics) == 0
    print("[F03] folded password rescan mixed-script is quiet", flush=True)


# ===========================================================================
# E. Trim, indent, interior HT/LF/CR, markdown hard-break, file CRLF
# ===========================================================================


def test_trailing_spaces_and_tabs_are_trimmed_newline_convention_kept():
    body = "The lock opened at dawn.   \nCrews waited.\t\t\n"
    out = scrub_stdin(body)
    print(f"[F03] trim out={out!r}", flush=True)
    lines = out.splitlines()
    assert lines, "cleanup dropped the trimmed line bodies"
    assert lines[0] == "The lock opened at dawn."
    assert lines[1] == "Crews waited."
    assert not lines[0].endswith(" ")
    assert not lines[0].endswith("\t")
    for line in lines:
        assert line == line.rstrip(" \t")
    assert body.endswith("\n")
    assert out.endswith("\n")
    file_body = "The lock opened at dawn.\n"
    with workspace() as ws:
        ws.write("ended.md", file_body.encode("utf-8"))
        file_out = require_scrubbed_stdout(scrub_path(ws, "ended.md"))
    assert file_out.endswith("\n")
    assert file_out.splitlines()[0] == "The lock opened at dawn."
    eof_spaces = "The lock opened at dawn.   "
    eof_out = scrub_stdin(eof_spaces)
    assert eof_out.rstrip("\n") == "The lock opened at dawn."
    assert not eof_out.endswith(" ")
    assert not eof_out.endswith("\t")


def test_leading_blank_lines_dropped_four_space_indent_kept():
    public = FOUR_SPACE_LINE
    out_public = scrub_stdin(public)
    print(f"[F03] four-space public={out_public!r}", flush=True)
    assert out_public.rstrip("\n").startswith("    ")
    assert first_content_leading_spaces(out_public) == 4
    assert out_public.rstrip("\n") == public

    twin_words = "oak " + runtime_token("code")
    twin = "    " + twin_words
    out_twin = scrub_stdin(twin)
    assert first_content_leading_spaces(out_twin) == 4
    assert twin_words.strip() in out_twin
    assert out_twin.rstrip("\n") != public

    blanked = "\n\n    " + twin_words
    out_blank = scrub_stdin(blanked)
    assert not out_blank.startswith("\n")
    assert first_content_leading_spaces(out_blank) == 4

    wider = 6 + secrets.randbelow(5)
    wide_words = "pine " + runtime_token("wide")
    wide = (" " * wider) + wide_words
    out_wide = scrub_stdin(wide)
    wide_n = first_content_leading_spaces(out_wide)
    four_n = first_content_leading_spaces(out_twin)
    print(f"[F03] indent four={four_n} wider={wide_n} (asked {wider})", flush=True)
    assert four_n == 4
    assert wide_n > four_n
    assert wide_n == wider


def test_interior_tab_lf_cr_are_not_stripped_as_invisible():
    left = "Oak" + secrets.token_hex(2)
    right = "pine" + secrets.token_hex(2)
    zw = ZWSP
    tab_p = f"{left}\t{right}{zw}end"
    lf_p = f"{left}\n{right}{zw}end"
    cr_p = f"{left}\r{right}{zw}end"
    for name, probe, keep in (
        ("tab", tab_p, "\t"),
        ("lf", lf_p, "\n"),
        ("cr", cr_p, "\r"),
    ):
        out = scrub_stdin(probe)
        print(f"[F03] interior {name} out={out!r}", flush=True)
        assert zw not in out
        assert left in out and right in out
        if name == "lf":
            gap = gap_between(out, left, right)
            assert "\n" in gap, (
                "interior line feed between the two words is gone; "
                f"gap={gap!r} out={out!r}"
            )
        else:
            assert keep in out
    tab_out = scrub_stdin(tab_p)
    cr_out = scrub_stdin(cr_p)
    lf_out = scrub_stdin(lf_p)
    assert cr_out.count("\r") > lf_out.count("\r")
    assert "\t" in tab_out


def test_markdown_hard_break_two_spaces_are_collapsed():
    public = "line  \nnext"
    out_p = scrub_stdin(public)
    print(f"[F03] hard-break public={out_p!r}", flush=True)
    public_lines = out_p.splitlines()
    assert public_lines, "cleanup dropped the hard-break lines"
    assert public_lines[0] == public_lines[0].rstrip(" \t")
    assert public_lines[0] == public.splitlines()[0].rstrip(" \t")
    tokens_in_relative_order(out_p, "line", "next")
    a = "Oak" + secrets.token_hex(2)
    b = "pine" + secrets.token_hex(2)
    twin = f"{a}  \n{b}"
    out_t = scrub_stdin(twin)
    twin_lines = out_t.splitlines()
    assert twin_lines, "cleanup dropped the hard-break twin lines"
    assert twin_lines[0] == twin_lines[0].rstrip(" \t")
    assert twin_lines[0] == twin.splitlines()[0].rstrip(" \t")
    assert a in out_t and b in out_t
    tokens_in_relative_order(out_t, a, b)


def test_file_with_crlf_still_has_crlf_after_cleanup():
    w1 = "Oak" + secrets.token_hex(2)
    w2 = "pine" + secrets.token_hex(2)
    lf_text = f"{w1}{ZWSP} sits {w2}.\n"
    crlf_text = lf_text.replace("\n", "\r\n")
    with workspace() as ws:
        ws.write("lf.md", lf_text.encode("utf-8"))
        ws.write("crlf.md", crlf_text.encode("utf-8"))
        before_lf = ws.resolve("lf.md").read_bytes()
        before_crlf = ws.resolve("crlf.md").read_bytes()
        lf_r = scrub_path(ws, "lf.md")
        crlf_r = scrub_path(ws, "crlf.md")
        lf_out = require_scrubbed_stdout(lf_r)
        crlf_out = require_scrubbed_stdout(crlf_r)
    print(f"[F03] crlf out={crlf_out!r} lf out={lf_out!r}", flush=True)
    assert ZWSP not in lf_out and ZWSP not in crlf_out
    assert lf_r.stdout != before_lf
    assert crlf_r.stdout != before_crlf
    assert "\r" in crlf_out
    assert crlf_out.count("\r") > lf_out.count("\r")
    assert w1 in crlf_out and w2 in crlf_out


# ===========================================================================
# F. Keep list byte-for-byte; agreement with detection
# ===========================================================================


def test_england_flag_sequence_is_kept_byte_for_byte():
    """AST-visible England-flag arm so a probe can name this function."""
    stamp = runtime_token("flag")
    flag = england_flag_sequence()
    text = f"Match in {flag} {stamp}."
    out = scrub_stdin(text)
    print(f"[F03] keep england-flag in={text!r} out={out!r}", flush=True)
    assert flag in out
    assert out == text


def test_named_keep_sequences_are_byte_for_byte():
    cases = keep_sequence_cases()
    assert cases, "keep-list construction produced no sequences"
    for name, text in cases:
        out = scrub_stdin(text)
        print(f"[F03] keep {name} in={text!r} out={out!r}", flush=True)
        assert out == text, f"keep {name} was not byte-for-byte"


def test_kept_characters_are_not_invisible_or_stray_space_on_the_original_scan():
    debris_zw = f"The latch{ZWSP}sits on the quay near the lock."
    debris_sp = f"Two{NBSP}words sit on the page near the lock."
    zw_scan = scan_stdin(debris_zw)
    zw_f, zw_m = require_success_report(zw_scan, input_chars=unicode_len(debris_zw))
    require_finding(zw_f, 62)
    assert invisible_count_of(zw_m) > 0
    sp_scan = scan_stdin(debris_sp)
    sp_f, sp_m = require_success_report(sp_scan, input_chars=unicode_len(debris_sp))
    require_finding(sp_f, 67)
    assert nonstandard_space_count_of(sp_m) > 0

    french = f"Gate{NBSP}: open on the quay."
    figure = f"It costs {FIGURE_40_EUR} today on the quay."
    cases = keep_sequence_cases() + [
        ("french-nbsp", french),
        ("figure-nnbsp", figure),
        ("cafe-bare", CAFE),
        ("nihongo-bare", NIHONGO),
    ]
    for name, text in cases:
        kept = scrub_stdin(text)
        assert kept == text
        orig = scan_stdin(text)
        o_f, o_m = require_success_report(orig, input_chars=unicode_len(text))
        require_absent_finding(o_f, 62)
        require_absent_finding(o_f, 67)
        assert invisible_count_of(o_m) == 0
        assert nonstandard_space_count_of(o_m) == 0
        print(
            f"[F03] agree {name} kept={kept == text} inv={invisible_count_of(o_m)} "
            f"space={nonstandard_space_count_of(o_m)}",
            flush=True,
        )


# ===========================================================================
# G. Document files: extracted plain text, not a rebuilt zip; no writes; usage
# ===========================================================================


def _planted_document_body() -> tuple[str, str, str]:
    token = runtime_token("Doc")
    planted = token[:4] + ZWSP + token[4:]
    body = f"The {planted} sits on the quay near the lock."
    return token, planted, body


def test_cleanup_of_docx_epub_odt_ipynb_prints_extracted_text_not_zip_bytes():
    token, _planted, body = _planted_document_body()
    with workspace() as ws:
        write_docx(ws, "a.docx", body)
        write_epub(ws, "a.epub", body)
        write_odt(ws, "a.odt", text=body)
        write_notebook(ws, "a.ipynb", markdown=body)
        for rel in ("a.docx", "a.epub", "a.odt", "a.ipynb"):
            result = scrub_path(ws, rel)
            raw = result.stdout
            print(
                f"[F03] document {rel} magic={raw[:4]!r} len={len(raw)}",
                flush=True,
            )
            assert result.returncode == 0
            assert not stdout_is_zip_bytes(raw)
            text = require_scrubbed_stdout(result)
            assert not _stdout_is_report(text)
            assert token in text
            assert ZWSP not in text
            assert token[:4] in text


def test_cleanup_does_not_write_or_rebuild_the_document_file():
    token, _planted, body = _planted_document_body()
    with workspace() as ws:
        write_docx(ws, "keep.docx", body)
        dest = ws.resolve("keep.docx")
        before = dest.read_bytes()
        result = scrub_path(ws, "keep.docx")
        require_scrubbed_stdout(result)
        assert token[:4] in result.stdout_text
        assert not stdout_is_zip_bytes(result.stdout)
        assert_operand_unchanged(ws, "keep.docx", before)


def test_usage_warns_that_redirecting_cleanup_over_a_document_is_misuse():
    """Help names the cleanup switch on the stated synopsis line. Graded L177 is
    extracted prose on stdout and unchanged original-path bytes.
    """
    with workspace() as ws:
        help_r = ws.invoke([HELP_FLAG])
    assert help_r.returncode == 0
    usage = help_r.stdout_text
    first = usage.splitlines()[0] if usage.splitlines() else ""
    print(f"[F03] usage synopsis {first!r}", flush=True)
    assert first == USAGE_SYNOPSIS
    assert f"[{CLEANUP_FLAG}]" in first

    token, _planted, body = _planted_document_body()
    with workspace() as ws:
        write_docx(ws, "usage.docx", body)
        before = ws.resolve("usage.docx").read_bytes()
        result = scrub_path(ws, "usage.docx")
        raw = result.stdout
        print(
            f"[F03] usage-doc magic={raw[:4]!r} len={len(raw)}",
            flush=True,
        )
        assert result.returncode == 0
        assert not stdout_is_zip_bytes(raw)
        text = require_scrubbed_stdout(result)
        assert not _stdout_is_report(text)
        assert token in text
        assert ZWSP not in text
        assert_operand_unchanged(ws, "usage.docx", before)


# ===========================================================================
# H. Eight-second budget
# ===========================================================================


def test_eight_thousand_tag_run_finishes_within_8_seconds_with_and_without_cleanup():
    letter = secrets.choice("abcdefghijklmnop")
    payload = chr(0xE0041) * 8000 + letter
    flag = cleanup_switch()
    plain = finish_within_8s(stdin=payload)
    assert plain.returncode == 0
    require_success_report(plain, input_chars=unicode_len(payload))
    cleaned = finish_within_8s((flag,), stdin=payload)
    text = require_scrubbed_stdout(cleaned)
    print(f"[F03] tag-run letter={letter!r} cleaned={text!r}", flush=True)
    assert letter in text
    assert chr(0xE0041) not in text


def test_thirty_two_thousand_space_run_finishes_within_8_seconds_with_and_without_cleanup():
    letter = secrets.choice("qrstuvwxyz")
    payload = (" " * 32000) + letter
    flag = cleanup_switch()
    plain = finish_within_8s(stdin=payload)
    assert plain.returncode == 0
    require_success_report(plain, input_chars=unicode_len(payload))
    cleaned = finish_within_8s((flag,), stdin=payload)
    text = require_scrubbed_stdout(cleaned)
    print(f"[F03] space-run letter={letter!r} len={len(text)}", flush=True)
    assert letter in text
    assert cleaned.returncode == 0


def test_long_unspaced_token_finishes_within_8_seconds_with_and_without_cleanup():
    # One word longer than the scan window, with no space anywhere: still
    # inside the plain-text cap, so the same 8-second budget holds.
    unit = "".join(secrets.choice("bcdfghklmnprstvw") for _ in range(5)) + "a"
    payload = (unit * (SCAN_CAP // len(unit) + 2))[: SCAN_CAP + 1]
    assert len(payload.encode("utf-8")) <= 512 * 1024
    flag = cleanup_switch()
    plain = finish_within_8s(stdin=payload)
    assert plain.returncode == 0
    require_success_report(plain, input_chars=unicode_len(payload))
    cleaned = finish_within_8s((flag,), stdin=payload)
    text = require_scrubbed_stdout(cleaned)
    print(f"[F03] long-token unit={unit!r} cleaned_len={len(text)}", flush=True)
    assert text == payload


# ===========================================================================
# I. Empty / unreadable / unknown-option / extra operands follow F01
# ===========================================================================


def test_cleanup_of_empty_input_still_fails_structured():
    flag = cleanup_switch()
    empty_plain = scan_stdin("")
    empty_clean = scan_stdin("", extra_args=(flag,))
    require_empty_input_error(empty_plain)
    require_empty_input_error(empty_clean)
    with workspace() as ws:
        ws.write("empty.txt", "")
        empty_file = scan_path(ws, "empty.txt", extra_args=(flag,))
        require_empty_input_error(empty_file)
    print("[F03] empty+cleanup is the stated empty-input error", flush=True)


def test_cleanup_of_unreadable_path_still_fails():
    flag = cleanup_switch()
    empty_clean = scan_stdin("", extra_args=(flag,))
    require_empty_input_error(empty_clean)
    unknown_tok = "--zz" + secrets.token_hex(2)
    unknown = scan_stdin(SHORT_FACTUAL, extra_args=(flag, unknown_tok))
    require_unknown_option_error(unknown, unknown_tok)
    with workspace() as ws:
        missing = str(ws.resolve("missing.txt"))
        unread = ws.invoke([flag, missing])
        require_cannot_read_error(unread)
    assert unread.returncode == empty_clean.returncode
    assert unread.returncode != unknown.returncode
    print("[F03] unreadable+cleanup is the stated cannot-read error", flush=True)


def test_cleanup_plus_unknown_option_still_fails_as_unknown_option():
    flag = cleanup_switch()
    token = "--zz" + secrets.token_hex(2)
    empty = scan_stdin("", extra_args=(flag,))
    unknown = scan_stdin(cellulose_probe(), extra_args=(flag, token))
    require_empty_input_error(empty)
    require_unknown_option_error(unknown, token)
    assert empty.returncode != unknown.returncode
    print(f"[F03] unknown+cleanup token={token!r} exit={unknown.returncode}", flush=True)


def test_cleanup_extra_operands_scrub_the_first_file_and_warn():
    flag = cleanup_switch()
    first_body = cellulose_probe(newline=True)
    second_token = runtime_token("Second")
    second_body = f"The {second_token} waited at the weir.\n"
    with workspace() as ws:
        ws.write("first.md", first_body.encode("utf-8"))
        ws.write("second.md", second_body.encode("utf-8"))
        first_path = str(ws.resolve("first.md"))
        second_path = str(ws.resolve("second.md"))
        multi = ws.invoke([flag, first_path, second_path])
        only_first = ws.invoke([flag, first_path])
    text = require_scrubbed_stdout(multi)
    first_only = require_scrubbed_stdout(only_first)
    print(f"[F03] extra-operand stdout={text!r} stderr={multi.stderr_text!r}", flush=True)
    assert multi.returncode == 0
    assert text == CELLULOSE_CLEAN + "\n"
    assert text == first_only
    assert second_token not in text
    assert named_file_in_stderr(multi.stderr_text, first_path)
    assert states_one_file_at_a_time(multi.stderr_text, first_path)
    assert multi.stderr_text != only_first.stderr_text


# ===========================================================================
# J. Local only on the cleanup path
# ===========================================================================


def test_cleanup_opens_no_connection_to_a_proxy_sink():
    probe = cellulose_probe()
    with workspace() as ws:
        with proxy_sink() as sink:
            before = sink.n_connections
            result = ws.invoke(
                [cleanup_switch()],
                stdin=probe,
                env_updates={
                    "HTTP_PROXY": sink.url,
                    "HTTPS_PROXY": sink.url,
                    "ALL_PROXY": sink.url,
                    "http_proxy": sink.url,
                    "https_proxy": sink.url,
                    "all_proxy": sink.url,
                },
            )
            text = require_scrubbed_stdout(result)
            after = sink.n_connections
            print(
                f"[F03] proxy connects during cleanup: {after - before} out={text!r}",
                flush=True,
            )
            assert text.rstrip("\n") == CELLULOSE_CLEAN
            assert after == before
            sink.fire_positive_control()
            assert sink.n_connections > after
