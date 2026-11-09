# feature: F05
"""Binary files and text encoding, observed through ordinary searches."""

from __future__ import annotations

import json

from _helpers import make_tree, unique_token
from F01_helpers import assert_exit, err_lines, out_lines, tg
from F03_helpers import parse_json_stream
from F05_helpers import BINARY_EXTENSIONS, binary_note, first_nul, notes_in


def _binary_payload(tok: str, filler: int = 20000) -> bytes:
    """A file with ``tok`` on a line before its first NUL and on a line after it.

    The NUL sits past the first 8 KiB, so a detector that only sniffs the
    head of the file misses it.
    """
    return (f"{tok} before\n".encode() + b"y" * filler + b"\n\0\n" + f"{tok} after\n\0end\n".encode())


def _json_by_path(messages, kind):
    return {m["data"]["path"]["text"]: m["data"] for m in messages if m["type"] == kind}


# F05.T01
def test_walked_binary_file_is_skipped_in_every_output(tmp_path):
    tok = unique_token()
    other = unique_token()
    late = _binary_payload(tok)
    assert first_nul(late) > 8192
    make_tree(tmp_path / "w", {
        "late.txt": late,
        "early.txt": f"{tok}\0\n".encode(),
        "plain.txt": f"{tok} plain\n",
        "nomatch.txt": f"{other}\n",
        "bin_nomatch.txt": f"{other}\0\n".encode(),
    })

    r = tg(["--sort", "path", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"w/plain.txt:{tok} plain"], r.describe()

    r = tg(["-l", "--sort", "path", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["w/plain.txt"], r.describe()

    r = tg(["-c", "--sort", "path", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["w/plain.txt:1"], r.describe()

    # Live baseline: a non-matching text file is listed; non-matching and
    # matching binary files are not.
    r = tg(["--files-without-match", "--sort", "path", tok, "w"], cwd=tmp_path)
    assert out_lines(r) == ["w/nomatch.txt"], r.describe()

    # A tree whose only matches are inside binary files reports no match.
    make_tree(tmp_path / "b", {"late.txt": late, "early.txt": f"{tok}\0\n".encode()})
    r = tg([tok, "b"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b"", r.describe()
    r = tg(["-c", tok, "b"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b"", r.describe()


# F05.T02
def test_named_binary_file_prints_one_note_with_first_nul_offset(tmp_path):
    tok = unique_token()
    data = _binary_payload(tok, filler=3000 + len(tok))
    off = first_nul(data)
    make_tree(tmp_path, {"one.dat2": data, "text.txt": f"{tok} text\n"})

    # Filenames not shown (single named file): bare note, nothing else.
    r = tg([tok, "one.dat2"], cwd=tmp_path)
    assert_exit(r, "match")
    lines = out_lines(r)
    assert len(lines) == 1, r.describe()
    assert binary_note(lines[0]) == (None, off), r.describe()

    # Filenames shown: note prefixed by the path.
    r = tg(["--sort", "path", tok, "one.dat2", "text.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    lines = out_lines(r)
    assert binary_note(lines[0]) == ("one.dat2", off), r.describe()
    assert lines[1:] == [f"text.txt:{tok} text"], r.describe()
    assert len(notes_in(r)) == 1

    r = tg(["-l", tok, "one.dat2"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["one.dat2"], r.describe()

    # Counts include matches on both sides of the NUL.
    r = tg(["-c", tok, "one.dat2"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["2"], r.describe()
    make_tree(tmp_path, {"two.dat2": f"{tok} {tok}\n\0\n{tok}\n{tok} {tok}\n".encode()})
    r = tg(["--count-matches", tok, "two.dat2"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["5"], r.describe()
    r = tg(["-c", tok, "two.dat2"], cwd=tmp_path)
    assert out_lines(r) == ["3"], r.describe()


# F05.T03
def test_binary_option_shows_walked_binary_and_text_option_prints_lines(tmp_path):
    tok = unique_token()
    data = _binary_payload(tok)
    off = first_nul(data)
    make_tree(tmp_path / "w", {"bin.txt": data, "plain.txt": f"{tok} plain\n"})

    r = tg(["--binary", "--sort", "path", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    lines = out_lines(r)
    assert len(lines) == 2, r.describe()
    assert binary_note(lines[0]) == ("w/bin.txt", off), r.describe()
    assert lines[1] == f"w/plain.txt:{tok} plain", r.describe()

    r = tg(["--text", "--sort", "path", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert notes_in(r) == [], r.describe()
    assert out_lines(r) == [
        f"w/bin.txt:{tok} before",
        f"w/bin.txt:{tok} after",
        f"w/plain.txt:{tok} plain",
    ], r.describe()

    # -a spelling of the text option on a named binary file.
    r = tg(["-a", tok, "w/bin.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"{tok} before", f"{tok} after"], r.describe()


# F05.T04
def test_json_binary_offset_and_bytes_searched(tmp_path):
    tok = unique_token()
    data = _binary_payload(tok)
    off = first_nul(data)
    make_tree(tmp_path / "w", {"bin.txt": data, "plain.txt": f"{tok} plain\n"})

    r = tg(["--json", tok, "w/bin.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    msgs = parse_json_stream(r)  # every line is a JSON message: no note line
    matches = [m["data"] for m in msgs if m["type"] == "match"]
    assert matches, r.describe()
    texts = [m["lines"]["text"] for m in matches]
    assert texts == [f"{tok} before\n", f"{tok} after\n"], r.describe()
    end = _json_by_path(msgs, "end")["w/bin.txt"]
    assert end["binary_offset"] == off, r.describe()
    assert end["stats"]["bytes_searched"] == off, r.describe()

    r = tg(["--json", tok, "w/plain.txt"], cwd=tmp_path)
    end = _json_by_path(parse_json_stream(r), "end")["w/plain.txt"]
    assert end["binary_offset"] is None, r.describe()

    r = tg(["--json", "--text", tok, "w/bin.txt"], cwd=tmp_path)
    msgs = parse_json_stream(r)
    end = _json_by_path(msgs, "end")["w/bin.txt"]
    assert end["binary_offset"] is None, r.describe()
    assert len([m for m in msgs if m["type"] == "match"]) == 2, r.describe()

    # Walked without --binary: no message names the binary file.
    r = tg(["--json", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    msgs = parse_json_stream(r)
    paths = {m["data"]["path"]["text"] for m in msgs if "path" in m["data"]}
    assert paths == {"w/plain.txt"}, r.describe()

    # Walked with --binary: the binary file is shown, with its offset.
    r = tg(["--json", "--binary", tok, "w"], cwd=tmp_path)
    msgs = parse_json_stream(r)
    end = _json_by_path(msgs, "end")
    assert end["w/bin.txt"]["binary_offset"] == off, r.describe()
    assert end["w/bin.txt"]["stats"]["bytes_searched"] == off, r.describe()
    assert end["w/plain.txt"]["binary_offset"] is None, r.describe()


def _case_variant(ext: str, i: int) -> str:
    if i % 2:
        return ext.upper()
    return "".join(c.upper() if j % 2 == 0 else c for j, c in enumerate(ext))


# F05.T05
def test_known_binary_extensions_are_skipped_in_directory_searches(tmp_path):
    tok = unique_token()
    files = {}
    for i, ext in enumerate(BINARY_EXTENSIONS):
        files[f"lo/f{i}.{ext}"] = f"{tok} {ext}\n"
        files[f"mix/f{i}.{_case_variant(ext, i)}"] = f"{tok} {ext}\n"
    make_tree(tmp_path / "w", files)
    # Look-alike extensions that are not on the list are classified by content.
    make_tree(tmp_path / "w", {"ok/a.pngx": f"{tok} pngx\n", "ok/b.txt": f"{tok} txt\n",
                               "ok/c.xpdf": f"{tok} xpdf\n"})

    r = tg(["-l", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    listed = set(out_lines(r))
    assert listed == {"w/ok/a.pngx", "w/ok/b.txt", "w/ok/c.xpdf"}, (
        "listed extension files leaked: " + repr(sorted(listed - {"w/ok/a.pngx", "w/ok/b.txt", "w/ok/c.xpdf"})))

    r = tg([tok, "w/lo", "w/mix"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b"", r.describe()

    every = set(files) | {"ok/a.pngx", "ok/b.txt", "ok/c.xpdf"}
    for opt in ("--binary", "--text"):
        r = tg([opt, "-l", tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert sorted(out_lines(r)) == sorted(f"w/{p}" for p in every), r.describe()

    # Named explicitly: never skipped by extension, each member on its own.
    for rel in sorted(files):
        r = tg([tok, f"w/{rel}"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [files[rel].rstrip("\n")], f"{rel}: {r.describe()}"


# F05.T06
def test_byte_order_marks_select_decoding(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {
        "u8.txt": b"\xef\xbb\xbf" + f"{tok} eight\n".encode("utf-8"),
        "le.txt": b"\xff\xfe" + f"{tok} little é\n".encode("utf-16-le"),
        "be.txt": b"\xfe\xff" + f"{tok} big é\n".encode("utf-16-be"),
        "plain.txt": f"{tok} café\n".encode("utf-8"),
        "nobom16.txt": f"{tok} nobom\n".encode("utf-16-le"),
    })

    for name, want in (("u8.txt", f"{tok} eight"), ("le.txt", f"{tok} little é"),
                       ("be.txt", f"{tok} big é")):
        r = tg([f"^{tok}", name], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [want], f"{name}: {r.describe()}"
        # Decoded text is matched, including non-ASCII content.
        r = tg(["é|eight", name], cwd=tmp_path)
        assert_exit(r, "match")

    # No mark: UTF-8.
    r = tg([f"^{tok} café$", "plain.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"{tok} café"]
    # A BOM-less UTF-16 file is not sniffed as UTF-16.
    r = tg([f"{tok} nobom", "nobom16.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b"", r.describe()


# F05.T07
def test_named_encodings_bom_override_none_and_later_wins(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {
        "lat.txt": f"{tok} café\n".encode("latin-1"),
        "sj.txt": f"{tok} 日本語\n".encode("shift_jis"),
        "u8bom.txt": b"\xef\xbb\xbf" + f"{tok} café\n".encode("utf-8"),
        "le.txt": b"\xff\xfe" + f"{tok} café\n".encode("utf-16-le"),
    })
    lat_pat = f"{tok} café"

    # Live baseline: under auto the latin-1 byte is not é.
    r = tg([lat_pat, "lat.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    for label in ("latin1", "iso-8859-1", "windows-1252"):
        r = tg(["-E", label, lat_pat, "lat.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [lat_pat], f"{label}: {r.describe()}"

    sj_pat = f"{tok} 日本語"
    r = tg([sj_pat, "sj.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    r = tg(["--encoding", "shift_jis", sj_pat, "sj.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [sj_pat], r.describe()

    # A byte-order mark overrides the label.
    for name in ("u8bom.txt", "le.txt"):
        r = tg(["-E", "latin1", f"^{lat_pat}$", name], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [lat_pat], f"{name}: {r.describe()}"

    # none: no sniffing, so the UTF-8 mark is text and UTF-16 is not decoded.
    r = tg(["-E", "none", f"^{tok}", "u8bom.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    r = tg([f"^{tok}", "u8bom.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    r = tg(["-E", "none", tok, "le.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b"", r.describe()

    # Between --encoding and --no-encoding the later one wins.
    r = tg(["-E", "latin1", "--no-encoding", lat_pat, "lat.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    r = tg(["--no-encoding", "-E", "latin1", lat_pat, "lat.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    r = tg(["-E", "none", "--no-encoding", f"^{tok}", "u8bom.txt"], cwd=tmp_path)
    assert_exit(r, "match")


# F05.T08
def test_invalid_utf8_repair_and_offset_coordinates(tmp_path):
    tok = unique_token()
    raw = b"a\xff\xfe\n" + b"\xff" + tok.encode() + b"\n"
    make_tree(tmp_path, {
        "bad.txt": raw,
        "badbin.txt": b"ab\xffcd\0\n" + tok.encode() + b"\n",
        "le.txt": b"\xff\xfe" + f"xx\n{tok}\n".encode("utf-16-le"),
    })

    for enc in ([], ["-E", "none"]):
        r = tg(enc + ["-c", "\\x{FFFD}", "bad.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == ["2"], r.describe()
        r = tg(enc + [f"^\\x{{FFFD}}{tok}$", "bad.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        # Positions in text output are original-file bytes: line 2 starts at
        # byte 4 of the file and the token is its 2nd byte.
        r = tg(enc + ["-n", "--column", "-b", tok, "bad.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        line = out_lines(r)
        assert len(line) == 1 and line[0].startswith(f"2:{raw.index(tok.encode()) - 4 + 1}:{4}:"), r.describe()

    # Binary offset in text output: original bytes too.
    r = tg([tok, "badbin.txt"], cwd=tmp_path)
    assert [binary_note(l) for l in out_lines(r)] == [(None, 5)], r.describe()

    # JSON: line text carries U+FFFD; submatch offsets index that text.
    r = tg(["--json", tok, "bad.txt"], cwd=tmp_path)
    m = [x["data"] for x in parse_json_stream(r) if x["type"] == "match"]
    assert len(m) == 1, r.describe()
    text = m[0]["lines"]["text"]
    assert text == "�" + tok + "\n", r.describe()
    sm = m[0]["submatches"]
    assert len(sm) == 1
    enc_text = text.encode("utf-8")
    assert enc_text[sm[0]["start"]:sm[0]["end"]] == tok.encode(), r.describe()

    # Transcoded UTF-16: offsets are in the decoded text and exclude the BOM.
    decoded_offset = len("xx\n".encode("utf-8"))
    r = tg(["-n", "-b", tok, "le.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"2:{decoded_offset}:{tok}"], r.describe()
    r = tg(["--json", tok, "le.txt"], cwd=tmp_path)
    m = [x["data"] for x in parse_json_stream(r) if x["type"] == "match"]
    assert m[0]["absolute_offset"] == decoded_offset, r.describe()
    assert (m[0]["submatches"][0]["start"], m[0]["submatches"][0]["end"]) == (0, len(tok))


# F05.T09
def test_unknown_encoding_label_is_rejected(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"a.txt": f"{tok}\n"})
    for label in (unique_token("enc"), "utf-17", "latin-99"):
        r = tg(["-E", label, tok, "a.txt"], cwd=tmp_path)
        assert_exit(r, "error")
        assert r.stdout == b"", r.describe()
        assert err_lines(r), r.describe()
    # Control: valid labels are accepted on the same file.
    for label in ("auto", "none", "utf-8", "", "  "):
        r = tg(["-E", label, tok, "a.txt"], cwd=tmp_path)
        assert_exit(r, "match")


# F05.T07 regression — FP-05.03, FP-05.06, FP-05.07, FP-05.08

def test_decoding_families_surrogates_and_invalid_sequences(tmp_path):
    cases = [("utf-16le", "utf-16-le", "oak𝄞é"), ("utf-16be", "utf-16-be", "elm😀é"),
             ("windows-1251", "cp1251", "Привет"), ("koi8-r", "koi8-r", "Москва"),
             ("gbk", "gbk", "中文"), ("big5", "big5", "繁體"), ("euc-kr", "euc_kr", "한국"),
             ("iso-8859-7", "iso8859-7", "Ελλάδα")]
    for i, (label, codec, text) in enumerate(cases):
        name = f"enc{i}.txt"
        make_tree(tmp_path, {name: (text + "\n").encode(codec)})
        r = tg(["-E", label, text, name], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [text]
    for endian, mark in (("le", b"\xff\xfe"), ("be", b"\xfe\xff")):
        make_tree(tmp_path, {"bom.txt": mark + "needle😀\n".encode("utf-16-" + endian)})
        assert out_lines(tg(["😀", "bom.txt"], cwd=tmp_path)) == ["needle😀"]
    make_tree(tmp_path, {"western.txt": b"coin \x80\n", "broken.txt": b"a\xe2\x82\nb\xf0\x9f\x92",
                         "binary.txt": b"needle\0tail\n"})
    for label in ("latin1", "iso-8859-1", "windows-1252"):
        assert out_lines(tg(["-E", label, "€", "western.txt"], cwd=tmp_path)) == ["coin €"]
    for enc in ([], ["-E", "none"]):
        assert out_lines(tg([*enc, "�", "broken.txt"], cwd=tmp_path)) == ["a�", "b�"]
    for raw in (b"oak\xe2\x82", b"elm\xf0\x9f\x92"):
        (tmp_path / "truncated.txt").write_bytes(raw)
        for enc in ([], ["-E", "none"]):
            r = tg([*enc, "�", "truncated.txt"], cwd=tmp_path)
            assert_exit(r, "match")
            assert out_lines(r) == [raw[:3].decode() + "�"]
    for flags in (["--binary", "--text"], ["--text", "--binary"]):
        r = tg([*flags, "needle", "binary.txt"], cwd=tmp_path)
        assert r.stdout == b"needle\0tail\n"


# F05.T05 regression — FP-05.05

def test_extension_skip_does_not_open_content(tmp_path):
    from F00_observations import ReadEvents
    root = make_tree(tmp_path / "w", {"asset.zip": "needle\n", "plain.txt": "needle\n"})
    with ReadEvents([root / "asset.zip"]) as events:
        r = tg(["needle", "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == ["w/plain.txt:needle"]
        assert events.accessed() == set()
        assert_exit(tg(["--text", "needle", "w"], cwd=tmp_path), "match")
        assert events.accessed() == {root / "asset.zip"}


# F05.T07 regression — FP-05.10

def test_decoding_and_binary_flags_scan_past_stale_indexes(tmp_path):
    from contextlib import nullcontext
    from F06_helpers import build_index
    from F07_helpers import NoWatchServer, read_stats
    for mode in ("local", "server"):
        root = make_tree(tmp_path / mode, {"old.txt": "initial\n"})
        build_index(root)
        with NoWatchServer(root) if mode == "server" else nullcontext():
            make_tree(root, {"late.txt": "fresh needle\n"})
            for flags in (["-E", "none"], ["-E", "utf-8"], ["--text"], ["--binary"]):
                r = tg(["--stats", *flags, "needle", "."], cwd=root)
                assert_exit(r, "match")
                assert out_lines(r) == ["./late.txt:fresh needle"]
                assert read_stats(r)["path"] == "scan"
