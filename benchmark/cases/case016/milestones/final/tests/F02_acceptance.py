# feature: F02
"""Acceptance tests for twenty-format extraction, size caps, and the scan window."""

from __future__ import annotations

import json
import zipfile

import pytest

from _harness import workspace
from F01_helpers import (
    AI_REGISTER,
    SCAN_CAP,
    invisible_count_of,
    proxy_sink,
    require_absent_finding,
    require_finding,
    require_no_traceback,
    require_success_report,
    scan_path,
    scan_stdin,
    scanned_of,
    score_of,
    unicode_len,
    window_is_longer,
    window_is_not_longer,
)
from F02_helpers import (
    ARCHIVE_CAP,
    PLAIN_CAP,
    PLAIN_EXTS,
    ZIP_EXTS,
    assert_extract_has_words,
    assert_no_markup,
    check_file,
    extract_via_cleanup,
    guard_write,
    nudge_score,
    pad_file_to_size,
    require_binary_ledger_record,
    require_cannot_read_error,
    require_check_cannot_read,
    require_check_not_a_file,
    require_check_over_cap,
    require_empty_input_error,
    require_show_size_skip,
    runtime_token,
    score_in_check_reply,
    show_session,
    slop_extract_body,
    slop_extract_twin,
    spreadsheet_sheet_xml,
    stone_bridge_body,
    tokens_in_relative_order,
    window_body,
    write_docm,
    write_docx,
    write_epub,
    write_notebook,
    write_odp,
    write_ods,
    write_odt,
    write_plain,
    write_pptx_slides,
    write_xlsx,
    write_xlsm,
    write_zip_slop,
)


def _score_file(ws, relpath: str) -> tuple[object, object, int]:
    result = scan_path(ws, relpath)
    findings, metrics = require_success_report(result)
    score = score_of(metrics, findings=findings)
    print(f"[F02] scan {relpath!r} score={score} scanned={scanned_of(metrics)}", flush=True)
    return findings, metrics, score


# ===========================================================================
# A. Nine plain-text extensions; leading mark is not prose
# ===========================================================================


@pytest.mark.parametrize("ext", PLAIN_EXTS)
def test_nine_plain_text_extensions_extract_and_score_slop(ext):
    body = slop_extract_body()
    with workspace() as ws:
        rel = f"note{ext}"
        write_plain(ws, rel, body)
        extract = extract_via_cleanup(ws, rel)
        findings, metrics, score = _score_file(ws, rel)
    assert_extract_has_words(extract, "delve", "game-changer")
    assert score >= 40
    print(f"[F02] {ext} extract_len={unicode_len(extract)} score={score}", flush=True)
    assert findings is not None
    assert metrics is not None


def test_leading_utf8_bom_is_not_prose_and_not_an_invisible_finding():
    body = slop_extract_twin()
    bom = b"\xef\xbb\xbf" + body.encode("utf-8")
    with workspace() as ws:
        write_plain(ws, "plain.md", body)
        ws.write("bom.md", bom)
        plain_extract = extract_via_cleanup(ws, "plain.md")
        bom_extract = extract_via_cleanup(ws, "bom.md")
        p_f, p_m, p_score = _score_file(ws, "plain.md")
        b_f, b_m, b_score = _score_file(ws, "bom.md")
    assert_extract_has_words(plain_extract, "delve", "game-changer")
    assert_extract_has_words(bom_extract, "delve", "game-changer")
    require_absent_finding(b_f, 62)
    require_absent_finding(p_f, 62)
    assert scanned_of(b_m, chars=unicode_len(body)) == unicode_len(body)
    assert scanned_of(p_m, chars=unicode_len(body)) == unicode_len(body)
    assert invisible_count_of(b_m) == invisible_count_of(p_m)
    assert p_score >= 40
    assert b_score >= 40
    print(
        f"[F02] utf8 bom scanned={scanned_of(b_m)} invisible={invisible_count_of(b_m)}",
        flush=True,
    )


def test_utf16_with_bom_plain_text_decodes_without_invisible_finding():
    body = slop_extract_twin()
    payload = body.encode("utf-16")
    with workspace() as ws:
        write_plain(ws, "plain.txt", body)
        ws.write("wide.txt", payload)
        extract = extract_via_cleanup(ws, "wide.txt")
        p_f, p_m, _p_score = _score_file(ws, "plain.txt")
        w_f, w_m, w_score = _score_file(ws, "wide.txt")
    assert_extract_has_words(extract, "delve", "game-changer")
    require_absent_finding(w_f, 62)
    assert scanned_of(w_m, chars=unicode_len(body)) == unicode_len(body)
    assert scanned_of(w_m) == scanned_of(p_m)
    assert invisible_count_of(w_m) == invisible_count_of(p_m)
    assert w_score >= 40
    print(
        f"[F02] utf16 extract has words scanned={scanned_of(w_m)} score={w_score}",
        flush=True,
    )


# ===========================================================================
# B. Zip-based formats: visible text, no markup, score at least 40
# ===========================================================================


@pytest.mark.parametrize("ext", ZIP_EXTS)
def test_zip_based_slop_extracts_distinctive_words_without_markup_and_scores_at_least_40(
    ext,
):
    body = slop_extract_body()
    with workspace() as ws:
        rel = f"sample{ext}"
        write_zip_slop(ws, rel, body)
        extract = extract_via_cleanup(ws, rel)
        _findings, _metrics, score = _score_file(ws, rel)
    assert_extract_has_words(extract, "delve", "game-changer")
    assert_no_markup(extract)
    assert score >= 40
    print(f"[F02] zip {ext} score={score} extract_len={unicode_len(extract)}", flush=True)


def test_markdown_and_office_round_trip_keep_distinctive_words():
    body = slop_extract_body()
    round_trip = (".md", ".docx", ".pptx", ".xlsx", ".odt", ".epub")
    with workspace() as ws:
        for ext in round_trip:
            rel = f"same{ext}"
            if ext == ".md":
                write_plain(ws, rel, body)
            else:
                write_zip_slop(ws, rel, body)
            extract = extract_via_cleanup(ws, rel)
            _f, _m, score = _score_file(ws, rel)
            print(f"[F02] round-trip {ext} score={score}", flush=True)
            assert_extract_has_words(extract, "delve", "game-changer")
            assert score >= 40
            if ext != ".md":
                assert_no_markup(extract)


def test_docm_yields_visible_paragraph_text_without_markup():
    token = runtime_token("Para")
    paragraph = (
        f"The main document records {token} on this page. "
        "Crews stacked the blocks in three even rows."
    )
    with workspace() as ws:
        write_docm(ws, "memo.docm", paragraph)
        extract = extract_via_cleanup(ws, "memo.docm")
    print(f"[F02] docm extract={extract!r}", flush=True)
    assert_extract_has_words(extract, token, "Crews stacked the blocks")
    assert_no_markup(extract)


def test_stone_bridge_human_docx_scores_below_40():
    body = stone_bridge_body()
    with workspace() as ws:
        write_docx(ws, "human.docx", body)
        extract = extract_via_cleanup(ws, "human.docx")
        _f, _m, score = _score_file(ws, "human.docx")
    assert_extract_has_words(extract, "arches", "mortar", "invoice", "photograph")
    assert_no_markup(extract)
    assert score < 40
    print(f"[F02] stone-bridge docx score={score} extract_len={unicode_len(extract)}", flush=True)


# ===========================================================================
# C. Spreadsheet identity, OpenDocument runs, reading order
# ===========================================================================


@pytest.mark.parametrize("writer,ext", [(write_xlsx, ".xlsx"), (write_xlsm, ".xlsm")])
def test_spreadsheet_shared_and_inline_strings_follow_cell_order_with_boundary(
    writer, ext
):
    unused = runtime_token("Unused")
    token_a = runtime_token("Alpha")
    token_b = runtime_token("Bravo")
    inline = runtime_token("Inline")
    typed = runtime_token("Typed")
    cached = runtime_token("Cached")
    oor_index = str(10_000_000 + int(runtime_token("n")[-6:], 16) % 9_000_000)
    non_numeric = runtime_token("Idx")
    formula = 'CONCATENATE("formula-source-only")'
    assert cached not in formula
    xml = spreadsheet_sheet_xml(
        shared_indices=("2", "1"),
        inline=(inline,),
        string_typed=(typed,),
        formula_cache=((formula, cached),),
        extra_cells=(
            "<c><v>42</v></c>"
            '<c t="s"><v>-1</v></c>'
            f'<c t="s"><v>{oor_index}</v></c>'
            f'<c t="s"><v>{non_numeric}</v></c>'
        ),
    )
    with workspace() as ws:
        writer(
            ws,
            f"book{ext}",
            shared_strings=(unused, token_a, token_b),
            sheet_xml=xml,
        )
        extract = extract_via_cleanup(ws, f"book{ext}")
    print(f"[F02] spreadsheet {ext} extract={extract!r}", flush=True)
    assert_extract_has_words(extract, token_a, token_b, inline, typed, cached)
    assert unused not in extract
    assert oor_index not in extract, (
        f"out-of-range shared-string index {oor_index!r} treated as text: "
        f"{extract!r}"
    )
    assert non_numeric not in extract, (
        f"non-numeric shared-string index {non_numeric!r} treated as text: "
        f"{extract!r}"
    )
    tokens_in_relative_order(extract, token_b, token_a)
    glued = token_b + token_a
    assert glued not in extract, f"cells concatenated with no boundary: {extract!r}"
    assert_no_markup(extract)


@pytest.mark.parametrize("writer,ext", [(write_odt, ".odt"), (write_odp, ".odp"), (write_ods, ".ods")])
def test_opendocument_preserves_linked_text_and_explicit_whitespace(writer, ext):
    xml_body = (
        "<text:p>Keep <text:a>linked <text:span>words</text:span></text:a> here.</text:p>"
        '<text:p>two<text:s text:c="2"/>words<text:tab/>tab<text:line-break/>line.</text:p>'
    )
    with workspace() as ws:
        writer(ws, f"linked{ext}", xml_body)
        extract = extract_via_cleanup(ws, f"linked{ext}")
    print(f"[F02] opendocument {ext} extract={extract!r}", flush=True)
    assert "Keep linked words here." in extract
    idx = extract.find("Keep linked words here.")
    rest = extract[idx:]
    two = rest.find("two  words")
    assert two != -1, f"missing two-space run: {extract!r}"
    after = rest[two:]
    tab_at = after.find("\t")
    assert tab_at != -1, f"missing tab after two-space run: {extract!r}"
    named = "two  words" + "\t" + "tab" + "\n" + "line."
    assert named in rest, f"named OpenDocument sequence missing: {extract!r}"
    assert_no_markup(extract)


@pytest.mark.parametrize("ext", [".pptx", ".pptm"])
def test_slides_emit_visible_text_in_slide_order(ext):
    token2 = runtime_token("SlideTwo")
    token10 = runtime_token("SlideTen")
    with workspace() as ws:
        write_pptx_slides(
            ws,
            f"deck{ext}",
            (("slide2.xml", token2), ("slide10.xml", token10)),
            later_numbered_first=True,
        )
        extract = extract_via_cleanup(ws, f"deck{ext}")
        path = ws.resolve(f"deck{ext}")
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if "slide" in n]
    print(f"[F02] slides {ext} namelist={names} extract={extract!r}", flush=True)
    assert names[0].endswith("slide10.xml"), names
    tokens_in_relative_order(extract, token2, token10)
    assert_no_markup(extract)


@pytest.mark.parametrize("writer,ext", [(write_xlsx, ".xlsx"), (write_xlsm, ".xlsm")])
def test_sheets_emit_cell_text_in_sheet_order(writer, ext):
    token2 = runtime_token("SheetTwo")
    token10 = runtime_token("SheetTen")
    sheet2 = spreadsheet_sheet_xml(inline=(token2,))
    sheet10 = spreadsheet_sheet_xml(inline=(token10,))
    with workspace() as ws:
        writer(
            ws,
            f"book{ext}",
            sheets=(("sheet2.xml", sheet2), ("sheet10.xml", sheet10)),
            later_numbered_first=True,
        )
        extract = extract_via_cleanup(ws, f"book{ext}")
        path = ws.resolve(f"book{ext}")
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if "worksheets/sheet" in n]
    print(f"[F02] sheets {ext} namelist={names} extract={extract!r}", flush=True)
    assert names[0].endswith("sheet10.xml"), names
    tokens_in_relative_order(extract, token2, token10)
    assert_no_markup(extract)


def test_epub_reading_order_excludes_nav_style_script_and_survives_undeclared_prefix():
    para = runtime_token("Para")
    nav = runtime_token("Nav")
    style = runtime_token("Style")
    script = runtime_token("Script")
    token2 = runtime_token("ChapTwo")
    token10 = runtime_token("ChapTen")
    chapter2 = (
        f'<nav epub:type="toc"><ol><li>{nav}</li></ol></nav>'
        f"<style>{style}{{color:red}}</style>"
        f"<script>var x = '{script}';</script>"
        f'<p epub:type="bridgehead">{token2} {para}</p>'
    )
    chapter10 = f"<p>{token10}</p>"
    with workspace() as ws:
        write_epub(
            ws,
            "book.epub",
            chapters=(
                ("chapter2.xhtml", chapter2),
                ("chapter10.xhtml", chapter10),
            ),
            later_numbered_first=True,
        )
        extract = extract_via_cleanup(ws, "book.epub")
        path = ws.resolve("book.epub")
        with zipfile.ZipFile(path) as zf:
            names = list(zf.namelist())
    print(f"[F02] epub namelist={names} extract={extract!r}", flush=True)
    assert names[0].endswith("chapter10.xhtml"), names
    tokens_in_relative_order(extract, token2, token10)
    assert para in extract
    assert nav not in extract
    assert style not in extract
    assert script not in extract
    assert_no_markup(extract)


def test_epub_inline_emphasis_and_links_contribute_visible_text():
    inner = (
        "<p>Keep <em>this emphasized text</em> and "
        '<a href="#">this link</a>.</p>'
    )
    with workspace() as ws:
        write_epub(ws, "fmt.epub", chapters=(("chapter.xhtml", inner),))
        extract = extract_via_cleanup(ws, "fmt.epub")
    print(f"[F02] epub inline extract={extract!r}", flush=True)
    assert "Keep this emphasized text and this link." in extract
    assert_no_markup(extract)


# ===========================================================================
# D. Notebook: markdown only; invalid notebook is empty input
# ===========================================================================


def test_notebook_markdown_slop_is_scored_and_code_cell_is_not():
    body = slop_extract_body()
    code_token = runtime_token("CodeOnly")
    out_token = runtime_token("OutputOnly")
    with workspace() as ws:
        write_notebook(
            ws,
            "mixed.ipynb",
            markdown=body,
            code_source=f"# {code_token}\nprint(1)\n",
            output_text=out_token,
        )
        extract = extract_via_cleanup(ws, "mixed.ipynb")
        _f, _m, score = _score_file(ws, "mixed.ipynb")
    assert_extract_has_words(extract, "delve", "game-changer")
    assert code_token not in extract
    assert out_token not in extract
    assert score >= 40
    print(f"[F02] notebook mixed score={score}", flush=True)


def test_notebook_list_of_string_markdown_source_is_joined():
    body = slop_extract_body()
    join_token = runtime_token("JoinMark")
    cut = max(4, len(join_token) // 2)
    parts = [body + join_token[:cut], join_token[cut:]]
    joined = parts[0] + parts[1]
    assert join_token not in parts[0]
    assert join_token not in parts[1]
    assert joined.endswith(join_token)
    with workspace() as ws:
        write_notebook(ws, "listed.ipynb", markdown=parts)
        extract = extract_via_cleanup(ws, "listed.ipynb")
        _f, _m, score = _score_file(ws, "listed.ipynb")
    print(f"[F02] notebook list-source score={score} extract={extract!r}", flush=True)
    assert_extract_has_words(extract, "delve", "game-changer")
    assert join_token in extract, (
        f"list-of-string fragments were not joined into one contiguous extract; "
        f"token={join_token!r} extract={extract!r}"
    )
    assert score >= 40


def test_code_only_notebook_fails_as_empty_extracted_prose():
    body = slop_extract_body()
    with workspace() as ws:
        write_notebook(ws, "code.ipynb", code_source=body)
        result = scan_path(ws, "code.ipynb")
        empty = scan_stdin("")
    err = require_empty_input_error(result)
    require_empty_input_error(empty)
    require_no_traceback(result)
    print(f"[F02] code-only notebook err={err!r}", flush=True)
    assert result.returncode != 0


def test_invalid_json_notebook_fails_as_empty_extracted_prose():
    with workspace() as ws:
        ws.write("bad.ipynb", "{this is not json")
        result = scan_path(ws, "bad.ipynb")
        empty = scan_stdin("")
    err = require_empty_input_error(result)
    require_empty_input_error(empty)
    require_no_traceback(result)
    print(f"[F02] invalid json notebook err={err!r}", flush=True)


@pytest.mark.parametrize(
    "payload",
    [
        {"cells": {"not": "a list"}},
        {"cells": [None]},
        {"cells": [{"cell_type": "markdown", "source": None}]},
        {"cells": [{"cell_type": "markdown", "source": [1]}]},
    ],
    ids=["object-cells", "null-cell", "null-source", "int-list-source"],
)
def test_malformed_notebook_cells_fail_as_empty_extracted_prose(payload):
    with workspace() as ws:
        ws.write("malformed.ipynb", json.dumps(payload))
        result = scan_path(ws, "malformed.ipynb")
        empty = scan_stdin("")
    err = require_empty_input_error(result)
    require_empty_input_error(empty)
    require_no_traceback(result)
    print(f"[F02] malformed notebook {payload!r} err={err!r}", flush=True)


# ===========================================================================
# E. PDF / RTF / non-zip / empty zip
# ===========================================================================


@pytest.mark.parametrize("rel,header", [("slop.pdf", b"%PDF-1.4\n"), ("slop.rtf", b"{\\rtf1\n")])
def test_pdf_and_rtf_containing_slop_bytes_are_not_extracted_as_prose(rel, header):
    body = slop_extract_body()
    with workspace() as ws:
        ws.write(rel, header + body.encode("utf-8"))
        result = scan_path(ws, rel)
        empty = scan_stdin("")
    err = require_empty_input_error(result)
    require_empty_input_error(empty)
    require_no_traceback(result)
    print(f"[F02] {rel} not prose err={err!r}", flush=True)


@pytest.mark.parametrize("rel,header", [("note.pdf", b"%PDF-1.4\n"), ("note.rtf", b"{\\rtf1\n")])
def test_guard_records_pdf_and_rtf_as_binary_on_the_ledger(rel, header):
    slop = slop_extract_body() + "\n\n" + AI_REGISTER
    with workspace() as ws:
        ws.write_mode_flag("full")
        write_plain(ws, "slop.md", slop)
        ws.write(rel, header + slop.encode("utf-8"))
        _f, _m, md_score = _score_file(ws, "slop.md")
        assert md_score > 40
        guard_bin, bin_blob = guard_write(ws, rel)
        show_result, show_blob = show_session(ws)
        guard_md, md_blob = guard_write(ws, "slop.md")
    assert guard_bin.returncode == 0
    assert guard_md.returncode == 0
    assert show_result.returncode == 0
    assert bin_blob == "", f"guard nudged on {rel!r}: {bin_blob[:400]!r}"
    require_binary_ledger_record(show_blob, rel)
    assert md_blob, "in-cap slop Write produced no scoring nudge"
    assert nudge_score(md_blob, "slop.md") == md_score
    print(
        f"[F02] guard {rel} exit={guard_bin.returncode} "
        f"show_len={len(show_blob)} md_nudge_len={len(md_blob)}",
        flush=True,
    )


def test_non_zip_docx_fails_structured_without_traceback():
    with workspace() as ws:
        ws.write("fake.docx", b"PK\x03 truncated-not-a-zip")
        result = scan_path(ws, "fake.docx")
    err = require_cannot_read_error(result)
    require_no_traceback(result)
    print(f"[F02] non-zip docx err={err!r}", flush=True)


def test_zip_with_no_extractable_prose_fails_as_empty_input():
    with workspace() as ws:
        empty_zip = ws.resolve("empty.docx")
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        result = scan_path(ws, "empty.docx")
        empty = scan_stdin("")
    err = require_empty_input_error(result)
    require_empty_input_error(empty)
    require_no_traceback(result)
    print(f"[F02] empty zip err={err!r}", flush=True)


# ===========================================================================
# F. 262,144-character window on extracted prose
# ===========================================================================


def test_extracted_prose_at_cap_is_not_longer_than_window():
    body = window_body(SCAN_CAP)
    with workspace() as ws:
        write_docx(ws, "at.docx", body)
        result = scan_path(ws, "at.docx")
        size = ws.resolve("at.docx").stat().st_size
    findings, metrics = require_success_report(result, input_chars=SCAN_CAP)
    assert scanned_of(metrics, chars=SCAN_CAP) == SCAN_CAP
    assert window_is_not_longer(metrics)
    print(
        f"[F02] at-cap zip bytes={size} scanned={scanned_of(metrics)} "
        f"not_longer={window_is_not_longer(metrics)}",
        flush=True,
    )
    assert findings is not None
    assert size < SCAN_CAP


def test_extracted_prose_one_past_cap_is_longer_and_scans_262144():
    body = window_body(SCAN_CAP + 1)
    with workspace() as ws:
        write_docx(ws, "over.docx", body)
        result = scan_path(ws, "over.docx")
        size = ws.resolve("over.docx").stat().st_size
    findings, metrics = require_success_report(result, input_chars=SCAN_CAP + 1)
    assert scanned_of(metrics, chars=SCAN_CAP + 1) == SCAN_CAP
    assert window_is_longer(metrics)
    print(
        f"[F02] over-cap zip bytes={size} scanned={scanned_of(metrics)} "
        f"longer={window_is_longer(metrics)}",
        flush=True,
    )
    assert findings is not None
    assert size < SCAN_CAP


def test_character_layer_ignores_invisible_mark_only_past_extracted_window():
    past = window_body(SCAN_CAP) + "\u200b"
    inside = "The lock opened at dawn." + "\u200b" + " Crews cleared ice."
    with workspace() as ws:
        write_docx(ws, "past.docx", past)
        write_docx(ws, "inside.docx", inside)
        past_r = scan_path(ws, "past.docx")
        inside_r = scan_path(ws, "inside.docx")
    past_f, past_m = require_success_report(past_r, input_chars=unicode_len(past))
    inside_f, _inside_m = require_success_report(
        inside_r, input_chars=unicode_len(inside)
    )
    require_finding(inside_f, 62)
    require_absent_finding(past_f, 62)
    assert window_is_longer(past_m)
    print(
        f"[F02] past-window 62 absent; in-window 62 present; "
        f"past scanned={scanned_of(past_m)}",
        flush=True,
    )


# ===========================================================================
# G. Plugin on-disk caps; detector still reads the path
# ===========================================================================


def test_detector_still_reads_a_path_over_the_plugin_plain_text_cap():
    body = slop_extract_body()
    with workspace() as ws:
        write_plain(ws, "over.md", body)
        pad_file_to_size(ws.resolve("over.md"), PLAIN_CAP + 1)
        size = ws.resolve("over.md").stat().st_size
        extract = extract_via_cleanup(ws, "over.md")
        findings, metrics, score = _score_file(ws, "over.md")
    print(f"[F02] detector oversize md bytes={size} score={score}", flush=True)
    assert size == PLAIN_CAP + 1
    assert_extract_has_words(extract, "delve", "game-changer")
    assert scanned_of(metrics) <= SCAN_CAP
    assert score >= 40
    assert findings is not None


def test_detector_still_reads_a_path_over_the_plugin_archive_cap():
    body = slop_extract_body()
    with workspace() as ws:
        write_docx(ws, "over.docx", body)
        pad_file_to_size(ws.resolve("over.docx"), ARCHIVE_CAP + 1)
        size = ws.resolve("over.docx").stat().st_size
        extract = extract_via_cleanup(ws, "over.docx")
        _f, metrics, score = _score_file(ws, "over.docx")
    print(f"[F02] detector oversize docx bytes={size} score={score}", flush=True)
    assert size == ARCHIVE_CAP + 1
    assert_extract_has_words(extract, "delve", "game-changer")
    assert scanned_of(metrics) <= SCAN_CAP
    assert score >= 40


def _check_agrees_with_detector(ws, relpath: str, *, floor: int | None) -> tuple[int, str]:
    _f, metrics, det_score = _score_file(ws, relpath)
    result, blob = check_file(ws, relpath)
    assert result.returncode == 0
    assert blob.strip(), "check reply is empty"
    check_score = score_in_check_reply(blob, expected=det_score)
    print(
        f"[F02] check {relpath!r} detector={det_score} check={check_score}",
        flush=True,
    )
    assert check_score == det_score
    if floor is not None:
        assert det_score >= floor
        assert check_score >= floor
    return det_score, blob


def _cannot_read_and_not_a_file_replies(ws) -> None:
    """Contrast arms: cannot-read and not-a-file are their own stated replies."""
    missing = "absent.md"
    result, blob = check_file(ws, missing)
    assert result.returncode == 0
    require_check_cannot_read(blob, str(ws.resolve(missing)))
    ws.mkdir("not-a-file")
    dir_result, dir_blob = check_file(ws, "not-a-file")
    assert dir_result.returncode == 0
    require_check_not_a_file(dir_blob, str(ws.resolve("not-a-file")), "not-a-file")
    print(
        f"[F02] cannot-read reply={blob!r} not-a-file reply={dir_blob!r}",
        flush=True,
    )


def test_check_scores_at_plain_text_cap_and_refuses_one_byte_over():
    slop = slop_extract_body()
    human = stone_bridge_body()
    with workspace() as ws:
        write_plain(ws, "at.md", slop)
        pad_file_to_size(ws.resolve("at.md"), PLAIN_CAP)
        write_plain(ws, "over.md", slop)
        pad_file_to_size(ws.resolve("over.md"), PLAIN_CAP + 1)
        write_plain(ws, "human.md", human)
        at_score, _at_blob = _check_agrees_with_detector(ws, "at.md", floor=40)
        _hf, _hm, human_det = _score_file(ws, "human.md")
        human_result, human_blob = check_file(ws, "human.md")
        over_result, over_blob = check_file(ws, "over.md")
        _cannot_read_and_not_a_file_replies(ws)
    assert human_result.returncode == 0
    assert over_result.returncode == 0
    human_check = score_in_check_reply(human_blob, expected=human_det)
    assert human_check == human_det
    assert human_check < 40
    require_check_over_cap(over_blob, cap_bytes=PLAIN_CAP, path=str(ws.resolve("over.md")))
    print(
        f"[F02] plain cap at={at_score} human={human_check} over_reply={over_blob!r}",
        flush=True,
    )


def test_check_scores_at_archive_cap_and_refuses_one_byte_over():
    slop = slop_extract_body()
    with workspace() as ws:
        write_docx(ws, "at.docx", slop)
        pad_file_to_size(ws.resolve("at.docx"), ARCHIVE_CAP)
        write_docx(ws, "over.docx", slop)
        pad_file_to_size(ws.resolve("over.docx"), ARCHIVE_CAP + 1)
        at_score, _at_blob = _check_agrees_with_detector(ws, "at.docx", floor=40)
        _of, _om, over_det = _score_file(ws, "over.docx")
        over_result, over_blob = check_file(ws, "over.docx")
        _cannot_read_and_not_a_file_replies(ws)
    assert over_result.returncode == 0
    require_check_over_cap(over_blob, cap_bytes=ARCHIVE_CAP, path=str(ws.resolve("over.docx")))
    print(
        f"[F02] archive cap at={at_score} over_det={over_det} over_reply={over_blob!r}",
        flush=True,
    )


def test_check_scores_notebook_between_plain_text_and_archive_cap_and_refuses_one_byte_over():
    slop = slop_extract_body()
    mid = PLAIN_CAP + 4096
    with workspace() as ws:
        write_notebook(ws, "mid.ipynb", markdown=slop, extra={"padding": "x"})
        pad_file_to_size(ws.resolve("mid.ipynb"), mid)
        write_notebook(ws, "over.ipynb", markdown=slop, extra={"padding": "x"})
        pad_file_to_size(ws.resolve("over.ipynb"), ARCHIVE_CAP + 1)
        size = ws.resolve("mid.ipynb").stat().st_size
        assert PLAIN_CAP < size < ARCHIVE_CAP
        mid_score, _mid_blob = _check_agrees_with_detector(ws, "mid.ipynb", floor=40)
        _of, _om, over_det = _score_file(ws, "over.ipynb")
        over_result, over_blob = check_file(ws, "over.ipynb")
        _cannot_read_and_not_a_file_replies(ws)
    assert over_result.returncode == 0
    require_check_over_cap(over_blob, cap_bytes=ARCHIVE_CAP, path=str(ws.resolve("over.ipynb")))
    print(
        f"[F02] notebook mid bytes={size} score={mid_score} over_det={over_det} "
        f"over_reply={over_blob!r}",
        flush=True,
    )


def test_guard_over_cap_write_exits_without_scoring_nudge():
    slop = slop_extract_body() + "\n\n" + AI_REGISTER
    with workspace() as ws:
        ws.write_mode_flag("full")
        write_plain(ws, "at.md", slop)
        write_plain(ws, "over.md", slop)
        pad_file_to_size(ws.resolve("over.md"), PLAIN_CAP + 1)
        _of, _om, det_score = _score_file(ws, "over.md")
        _af, _am, in_score = _score_file(ws, "at.md")
        assert in_score > 40
        assert det_score > 40
        guard_over, over_guard_blob = guard_write(ws, "over.md")
        show_result, show_blob = show_session(ws)
        _cannot_read_and_not_a_file_replies(ws)
        check_result, check_blob = check_file(ws, "over.md")
        guard_in, in_guard_blob = guard_write(ws, "at.md")
    assert guard_over.returncode == 0
    assert guard_in.returncode == 0
    assert show_result.returncode == 0
    assert check_result.returncode == 0
    assert in_guard_blob, "in-cap slop Write produced no scoring nudge"
    assert nudge_score(in_guard_blob, "at.md") == in_score
    assert over_guard_blob == "", (
        f"over-cap Write still carried a scoring nudge: {over_guard_blob[:400]!r}"
    )
    require_show_size_skip(show_blob, "over.md", cap_bytes=PLAIN_CAP)
    require_check_over_cap(check_blob, cap_bytes=PLAIN_CAP, path=str(ws.resolve("over.md")))
    print(
        f"[F02] guard over-cap exit={guard_over.returncode} "
        f"in_nudge_len={len(in_guard_blob)} show={show_blob!r} check={check_blob!r}",
        flush=True,
    )


# ===========================================================================
# H. Source-code extension on the detector is plain text
# ===========================================================================


@pytest.mark.parametrize("ext", [".py", ".js"])
def test_detector_reads_source_extension_as_plain_text(ext):
    body = slop_extract_body()
    with workspace() as ws:
        write_plain(ws, f"sample{ext}", body)
        extract = extract_via_cleanup(ws, f"sample{ext}")
        _f, _m, score = _score_file(ws, f"sample{ext}")
    assert_extract_has_words(extract, "delve", "game-changer")
    assert score >= 40
    print(f"[F02] detector {ext} score={score}", flush=True)


@pytest.mark.parametrize("ext", [".py", ".js"])
def test_guard_leaves_source_code_extension_alone(ext):
    slop = slop_extract_body() + "\n\n" + AI_REGISTER
    rel = f"sample{ext}"
    with workspace() as ws:
        ws.write_mode_flag("full")
        write_plain(ws, "slop.md", slop)
        write_plain(ws, rel, slop)
        _f, _m, md_score = _score_file(ws, "slop.md")
        assert md_score > 40
        guard_md, md_blob = guard_write(ws, "slop.md")
        guard_src, src_blob = guard_write(ws, rel)
    assert guard_md.returncode == 0
    assert guard_src.returncode == 0
    assert md_blob, "in-cap slop Write produced no scoring nudge"
    assert nudge_score(md_blob, "slop.md") == md_score
    assert src_blob == "", (
        f"source-code Write of {rel!r} produced a scoring nudge: "
        f"{src_blob[:400]!r}"
    )
    print(
        f"[F02] guard {rel} exit={guard_src.returncode} "
        f"nudge_len={len(src_blob)} md_nudge_len={len(md_blob)}",
        flush=True,
    )


# ===========================================================================
# I. Local only on the extraction path
# ===========================================================================


def test_office_and_epub_extraction_open_no_network():
    body = slop_extract_body()
    with workspace() as ws:
        write_docx(ws, "slop.docx", body)
        write_epub(ws, "slop.epub", body)
        with proxy_sink() as sink:
            before = sink.n_connections
            proxy_env = {
                "HTTP_PROXY": sink.url,
                "HTTPS_PROXY": sink.url,
                "ALL_PROXY": sink.url,
                "http_proxy": sink.url,
                "https_proxy": sink.url,
                "all_proxy": sink.url,
            }
            docx_extract = extract_via_cleanup(ws, "slop.docx")
            epub_extract = extract_via_cleanup(ws, "slop.epub")
            assert_extract_has_words(docx_extract, "delve", "game-changer")
            assert_extract_has_words(epub_extract, "delve", "game-changer")
            docx = ws.invoke(
                [str(ws.resolve("slop.docx"))],
                env_updates=proxy_env,
            )
            epub = ws.invoke(
                [str(ws.resolve("slop.epub"))],
                env_updates=proxy_env,
            )
            docx_f, docx_m = require_success_report(docx)
            epub_f, epub_m = require_success_report(epub)
            docx_score = score_of(docx_m, findings=docx_f)
            epub_score = score_of(epub_m, findings=epub_f)
            assert docx_score >= 40
            assert epub_score >= 40
            after = sink.n_connections
            print(
                f"[F02] proxy connects during extract: {after - before} "
                f"docx_score={docx_score} epub_score={epub_score}",
                flush=True,
            )
            assert after == before
            sink.fire_positive_control()
            assert sink.n_connections > after
