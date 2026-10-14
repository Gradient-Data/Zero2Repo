# feature: F01
"""FP-01: shared `.env` file format (quoting, comments, export, FIFO, streams).

Assertions stay at the PRD's precision: named bindings and values, no-value
versus empty string versus absence, skipped invalid lines that still leave a
later valid line, default `.env` / UTF-8 file decode and write, and Unix FIFO
as a load and file-location source. Warning wording, exception types, and
unlisted escape code points are not pinned.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from envfile import envfile_values, find_envfile, load_envfile, set_key  # noqa: F401 — public parse/load/write/location entries

from _harness import path_is_fifo, product_package_name, workspace
from _helpers import (
    bindings_from_file,
    bindings_from_text,
    environ_value,
    load_path,
    load_text,
    require_absent,
    require_binding,
    require_empty_string,
    require_labeled_line,
    require_no_value,
    require_script_success,
    require_utf8_text,
    run_without_product,
    unique_token,
    write_binding,
)

TRAILING_SPACE_SOURCE = "a='b c '"
TRAILING_SPACE_VALUE = "b c "


def _quoted_escape_source(name: str, letter: str, left: str = "", right: str = "") -> str:
    """Build ``NAME="left\\letterright"`` without f-string backslash pitfalls."""
    return name + '="' + left + "\\" + letter + right + '"'


# ---------------------------------------------------------------------------
# A. Names, values, whitespace, special-character names
# ---------------------------------------------------------------------------


def test_domain_example_org_binding():
    mapping = bindings_from_text("DOMAIN=example.org")
    print("source DOMAIN=example.org", flush=True)
    assert require_binding(mapping, "DOMAIN") == "example.org"


def test_runtime_unquoted_binding():
    name, value = unique_token(), unique_token()
    source = f"{name}={value}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    assert require_binding(mapping, name) == value


def test_spaces_around_name_equals_value_ignored():
    spaced = bindings_from_text(" a = b ")
    plain = bindings_from_text("a=b")
    print("public spaced vs plain", flush=True)
    assert require_binding(spaced, "a") == "b"
    assert require_binding(plain, "a") == "b"

    name, value = unique_token(), unique_token()
    runtime_plain = bindings_from_text(f"{name}={value}")
    runtime_spaced = bindings_from_text(f" {name} = {value} ")
    print(f"runtime spaced name={name!r}", flush=True)
    assert require_binding(runtime_plain, name) == value
    assert require_binding(runtime_spaced, name) == value


def test_single_quoted_name():
    mapping = bindings_from_text("'a'=b")
    print("source 'a'=b", flush=True)
    assert require_binding(mapping, "a") == "b"

    name, value = unique_token(), unique_token()
    runtime = bindings_from_text(f"'{name}'={value}")
    print(f"runtime quoted name {name!r}", flush=True)
    assert require_binding(runtime, name) == value
    require_absent(runtime, f"'{name}'")


def test_ugly_key_with_bracket_percent_dollar():
    mapping = bindings_from_text('uglyKey[%$="secret"')
    print('source uglyKey[%$="secret"', flush=True)
    assert require_binding(mapping, "uglyKey[%$") == "secret"

    prefix, value = unique_token(), unique_token()
    name = prefix + "[%$"
    runtime = bindings_from_text(name + '="' + value + '"')
    print(f"runtime ugly name {name!r}", flush=True)
    assert require_binding(runtime, name) == value


def test_runtime_name_with_special_chars():
    prefix, value = unique_token(), unique_token()
    name = prefix + "[%$"
    source = name + '="' + value + '"'
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    assert require_binding(mapping, name) == value


def test_quoted_values_keep_trailing_space():
    single = bindings_from_text("a='b c '")
    double = bindings_from_text('a="b c "')
    print("quoted trailing space on stream", flush=True)
    assert require_binding(single, "a") == TRAILING_SPACE_VALUE
    assert require_binding(double, "a") == TRAILING_SPACE_VALUE
    assert require_binding(single, "a").endswith(" ")
    assert require_binding(double, "a").endswith(" ")

    name, core = unique_token(), unique_token()
    trailing = core + " "
    runtime_single = bindings_from_text(f"{name}='{trailing}'")
    runtime_double = bindings_from_text(f'{name}="{trailing}"')
    print(f"runtime quoted trailing space {name!r}", flush=True)
    assert require_binding(runtime_single, name) == trailing
    assert require_binding(runtime_double, name) == trailing
    assert require_binding(runtime_single, name).endswith(" ")
    assert require_binding(runtime_double, name).endswith(" ")


def test_quoted_trailing_space_via_file_load_and_fifo():
    """Same rich source through mapping-file, load-file, and load-FIFO."""
    with workspace() as ws:
        file_path = ws.write("quoted.env", TRAILING_SPACE_SOURCE)
        from_file = bindings_from_file(file_path)
        print(f"mapping-file {TRAILING_SPACE_SOURCE!r}", flush=True)
        assert require_binding(from_file, "a") == TRAILING_SPACE_VALUE

        loaded_file = load_path(file_path)
        print("load regular file", flush=True)
        assert loaded_file.exception is None
        assert environ_value(loaded_file, "a") == TRAILING_SPACE_VALUE

        with ws.fifo("quoted.fifo", TRAILING_SPACE_SOURCE) as fifo:
            loaded_fifo = load_path(fifo)
        print("load FIFO", flush=True)
        assert loaded_fifo.exception is None
        assert environ_value(loaded_fifo, "a") == TRAILING_SPACE_VALUE


def test_unquoted_interior_space_and_tab_kept():
    space = bindings_from_text("a=b c")
    print("unquoted interior space", flush=True)
    assert require_binding(space, "a") == "b c"

    tab = bindings_from_text("a=b\tc")
    print("unquoted interior tab", flush=True)
    assert require_binding(tab, "a") == "b\tc"
    recorded = require_binding(tab, "a")
    assert "\t" in recorded
    assert recorded.split("\t") == ["b", "c"]

    name, left, right = unique_token(), unique_token(), unique_token()
    runtime_space = bindings_from_text(f"{name}={left} {right}")
    runtime_tab = bindings_from_text(f"{name}={left}\t{right}")
    print(f"runtime unquoted interior {name!r}", flush=True)
    assert require_binding(runtime_space, name) == f"{left} {right}"
    assert require_binding(runtime_tab, name) == f"{left}\t{right}"
    assert require_binding(runtime_tab, name).split("\t") == [left, right]


def test_unquoted_trailing_whitespace_stripped():
    interior = bindings_from_text("a=b c")
    trailing_space = bindings_from_text("a=b c ")
    trailing_tab = bindings_from_text("a=b c\t")
    print("unquoted trailing whitespace", flush=True)
    assert require_binding(interior, "a") == "b c"
    assert require_binding(trailing_space, "a") == "b c"
    assert require_binding(trailing_tab, "a") == "b c"
    assert not require_binding(trailing_space, "a").endswith(" ")
    assert "\t" not in require_binding(trailing_tab, "a")

    name, left, right = unique_token(), unique_token(), unique_token()
    core = f"{left} {right}"
    runtime_interior = bindings_from_text(f"{name}={core}")
    runtime_space = bindings_from_text(f"{name}={core} ")
    runtime_tab = bindings_from_text(f"{name}={core}\t")
    print(f"runtime unquoted trailing {name!r}", flush=True)
    assert require_binding(runtime_interior, name) == core
    assert require_binding(runtime_space, name) == core
    assert require_binding(runtime_tab, name) == core
    assert not require_binding(runtime_space, name).endswith(" ")
    assert "\t" not in require_binding(runtime_tab, name)


def test_unquoted_name_with_whitespace_not_a_binding():
    later_name, later_value = unique_token(), unique_token()
    source = f"a b=c\n{later_name}={later_value}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, "a b")
    require_absent(mapping, "a")
    assert require_binding(mapping, later_name) == later_value


def test_unquoted_name_with_hash_is_not_a_binding():
    later_name, later_value = unique_token(), unique_token()
    source = f"a#b=c\n{later_name}={later_value}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, "a#b")
    assert require_binding(mapping, later_name) == later_value

    prefix, later2, later2_value = unique_token(), unique_token(), unique_token()
    hashed = prefix + "#x"
    runtime = f"{hashed}=1\n{later2}={later2_value}"
    print(f"runtime hash-in-name {runtime!r}", flush=True)
    runtime_mapping = bindings_from_text(runtime)
    require_absent(runtime_mapping, hashed)
    assert require_binding(runtime_mapping, later2) == later2_value


# ---------------------------------------------------------------------------
# B. export directive vs a name that starts with export
# ---------------------------------------------------------------------------


def test_export_directive_ignored():
    exported = bindings_from_text("export a=b")
    plain = bindings_from_text("a=b")
    print("export a=b vs a=b", flush=True)
    assert require_binding(exported, "a") == "b"
    assert require_binding(plain, "a") == "b"
    require_absent(exported, "export a")


def test_export_with_spaces_and_quoted_name():
    mapping = bindings_from_text(" export 'a'=b")
    print("source  export 'a'=b", flush=True)
    assert require_binding(mapping, "a") == "b"
    require_absent(mapping, "export")


def test_name_starting_with_export_not_eaten():
    mapping = bindings_from_text("export export_a=1")
    print("source export export_a=1", flush=True)
    assert require_binding(mapping, "export_a") == "1"
    require_absent(mapping, "a")
    require_absent(mapping, "_a")


def test_export_port_is_named_port():
    mapping = bindings_from_text("export port=8000")
    print("source export port=8000", flush=True)
    assert require_binding(mapping, "port") == "8000"
    require_absent(mapping, "export port")


def test_runtime_export_directive():
    name, value = unique_token(), unique_token()
    mapping = bindings_from_text(f"export {name}={value}")
    print(f"export {name}={value}", flush=True)
    assert require_binding(mapping, name) == value
    require_absent(mapping, f"export {name}")

    inner = "export_" + unique_token()
    prefixed = bindings_from_text(f"export {inner}=1")
    print(f"export {inner}=1", flush=True)
    assert require_binding(prefixed, inner) == "1"


# ---------------------------------------------------------------------------
# C. Whole-line comments, trailing comments, glued hash
# ---------------------------------------------------------------------------


def test_hash_first_nonspace_is_comment():
    later, later_value = unique_token(), unique_token()
    mapping = bindings_from_text(f"# a=b\n{later}={later_value}")
    print("source # a=b then later binding", flush=True)
    require_absent(mapping, "a")
    require_absent(mapping, "# a")
    assert require_binding(mapping, later) == later_value

    indented_later, indented_value = unique_token(), unique_token()
    indented = bindings_from_text(f"  # comment\n{indented_later}={indented_value}")
    print("source   # comment then later binding", flush=True)
    require_absent(indented, "comment")
    require_absent(indented, "# comment")
    assert require_binding(indented, indented_later) == indented_value


def test_several_comment_lines_are_all_comments():
    later, later_value = unique_token(), unique_token()
    mapping = bindings_from_text(f"# a=b\n# c=d\n{later}={later_value}")
    print("several comment lines then later binding", flush=True)
    require_absent(mapping, "a")
    require_absent(mapping, "c")
    require_absent(mapping, "# a")
    require_absent(mapping, "# c")
    assert require_binding(mapping, later) == later_value


def test_whole_line_comment_then_later_binding():
    stolen, token, value = unique_token(), unique_token(), unique_token()
    source = f"# {stolen}=looks-like-a-binding\n{token}={value}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, stolen)
    assert require_binding(mapping, token) == value


def test_whitespace_separated_trailing_comment():
    mapping = bindings_from_text("a=b #c")
    print("source a=b #c", flush=True)
    assert require_binding(mapping, "a") == "b"

    name, value, tail = unique_token(), unique_token(), unique_token()
    runtime = bindings_from_text(f"{name}={value} #{tail}")
    print(f"runtime trailing comment {name!r}", flush=True)
    recorded = require_binding(runtime, name)
    assert recorded == value
    assert tail not in recorded


def test_glued_hash_is_value_text():
    mapping = bindings_from_text("a=b#c")
    print("source a=b#c", flush=True)
    assert require_binding(mapping, "a") == "b#c"

    name, value, tail = unique_token(), unique_token(), unique_token()
    runtime = bindings_from_text(f"{name}={value}#{tail}")
    print(f"runtime glued hash {name!r}", flush=True)
    assert require_binding(runtime, name) == f"{value}#{tail}"


def test_tab_before_hash_starts_comment():
    mapping = bindings_from_text("a=b\t#c")
    print("source a=b<tab>#c", flush=True)
    assert require_binding(mapping, "a") == "b"

    name, value, tail = unique_token(), unique_token(), unique_token()
    runtime = bindings_from_text(f"{name}={value}\t#{tail}")
    print(f"runtime tab comment {name!r}", flush=True)
    recorded = require_binding(runtime, name)
    assert recorded == value
    assert tail not in recorded
    assert "\t" not in recorded


def test_quoted_value_keeps_interior_hash():
    double = bindings_from_text('a="hello #world"')
    single = bindings_from_text("a='hello #world'")
    print("quoted interior hash", flush=True)
    assert require_binding(double, "a") == "hello #world"
    assert require_binding(single, "a") == "hello #world"

    left, right, name = unique_token(), unique_token(), unique_token()
    interior = f"{left} #{right}"
    runtime_double = bindings_from_text(f'{name}="{interior}"')
    runtime_single = bindings_from_text(f"{name}='{interior}'")
    print(f"runtime quoted hash {interior!r}", flush=True)
    assert require_binding(runtime_double, name) == interior
    assert require_binding(runtime_single, name) == interior


def test_runtime_comment_vs_glued_hash():
    name, value, tail = unique_token(), unique_token(), unique_token()
    baseline = bindings_from_text(f"{name}={value}")
    trailing = bindings_from_text(f"{name}={value} #{tail}")
    glued = bindings_from_text(f"{name}={value}#{tail}")
    print(f"comment vs glued name={name!r}", flush=True)
    assert require_binding(baseline, name) == value
    assert require_binding(trailing, name) == value
    assert tail not in require_binding(trailing, name)
    assert require_binding(glued, name) == f"{value}#{tail}"
    assert require_binding(trailing, name) != require_binding(glued, name)


# ---------------------------------------------------------------------------
# D. Single-quote vs double-quote escapes
# ---------------------------------------------------------------------------


def test_single_quote_backslash_and_quote_escapes():
    quote = bindings_from_text("a='b\\'c'")
    print(r"source a='b\'c'", flush=True)
    assert require_binding(quote, "a") == "b'c"

    backslash = bindings_from_text("a='b\\\\c'")
    print(r"source a='b\\c'", flush=True)
    recorded = require_binding(backslash, "a")
    assert recorded == "b\\c"
    assert recorded != "b\\\\c"

    left, right = unique_token(), unique_token()
    name_q, name_b = unique_token(), unique_token()
    runtime_quote = bindings_from_text(f"{name_q}='{left}\\'{right}'")
    runtime_bs = bindings_from_text(f"{name_b}='{left}\\\\{right}'")
    print("runtime single-quote escapes", flush=True)
    assert require_binding(runtime_quote, name_q) == left + "'" + right
    assert require_binding(runtime_bs, name_b) == left + "\\" + right
    assert require_binding(runtime_bs, name_b) != left + "\\\\" + right


def test_single_quote_n_is_not_newline():
    mapping = bindings_from_text("a='b\\nc'")
    print(r"source a='b\nc'", flush=True)
    recorded = require_binding(mapping, "a")
    assert recorded == "b\\nc"
    assert "\n" not in recorded
    assert list(recorded) == ["b", "\\", "n", "c"]


def test_double_quote_n_is_newline():
    mapping = bindings_from_text('a="b\\nc"')
    print(r'source a="b\nc"', flush=True)
    recorded = require_binding(mapping, "a")
    assert recorded == "b\nc"
    assert list(recorded) == ["b", "\n", "c"]


def test_double_quote_escaped_double_quote():
    mapping = bindings_from_text('a="b\\"c"')
    print(r'source a="b\"c"', flush=True)
    assert require_binding(mapping, "a") == 'b"c'


# PRD FP-01 listed double-quote escapes and the single character each denotes.
_LISTED_DOUBLE_QUOTE_ESCAPES = {
    "\\": "\\",
    "'": "'",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}


@pytest.mark.parametrize("letter", ["\\", "'", "a", "b", "f", "r", "t", "v"])
def test_double_quote_listed_escapes_are_not_two_char_literals(letter):
    # Ordinary text always follows the escape: a listed escape placed right
    # before the closing quote is not observed here.
    expected = _LISTED_DOUBLE_QUOTE_ESCAPES[letter]
    literal = "\\" + letter

    leading_name, after = unique_token(), unique_token()
    leading = bindings_from_text(_quoted_escape_source(leading_name, letter, "", after))
    recorded_leading = require_binding(leading, leading_name)
    print(f"escape {literal!r} then text recorded={recorded_leading!r}", flush=True)
    assert recorded_leading == expected + after, (
        f"listed escape {literal!r} followed by text did not decode to "
        f"{expected!r}: {recorded_leading!r}"
    )

    left, right, wrapped_name = unique_token(), unique_token(), unique_token()
    wrapped = bindings_from_text(_quoted_escape_source(wrapped_name, letter, left, right))
    recorded_wrapped = require_binding(wrapped, wrapped_name)
    print(f"wrapped escape {literal!r} recorded={recorded_wrapped!r}", flush=True)
    assert recorded_wrapped == left + expected + right, (
        f"wrapped listed escape {literal!r} did not insert {expected!r}: "
        f"{recorded_wrapped!r}"
    )


def test_unlisted_double_quote_backslash_letter_is_ordinary_text():
    name = unique_token()
    mapping = bindings_from_text(_quoted_escape_source(name, "q"))
    print(r'source NAME="\q"', flush=True)
    recorded = require_binding(mapping, name)
    print(f"unlisted letter recorded={recorded!r}", flush=True)

    left, right, wrapped_name = unique_token(), unique_token(), unique_token()
    wrapped = bindings_from_text(_quoted_escape_source(wrapped_name, "q", left, right))
    print("unlisted letter wrapped in runtime text", flush=True)
    recorded_wrapped = require_binding(wrapped, wrapped_name)
    assert left in recorded_wrapped, (
        f"wrapping prefix {left!r} missing from {recorded_wrapped!r}"
    )
    assert right in recorded_wrapped, (
        f"wrapping suffix {right!r} missing from {recorded_wrapped!r}"
    )


def test_backslash_n_differs_by_quote_kind():
    double = require_binding(bindings_from_text('a="b\\nc"'), "a")
    single = require_binding(bindings_from_text("a='b\\nc'"), "a")
    print(f"double={double!r} single={single!r}", flush=True)
    assert double != single
    assert double == "b\nc"
    assert single == "b\\nc"


def test_runtime_escaped_quotes():
    left, right = unique_token(), unique_token()
    name_n, name_dq, name_sq = unique_token(), unique_token(), unique_token()
    newline = bindings_from_text(_quoted_escape_source(name_n, "n", left, right))
    dquote = bindings_from_text(_quoted_escape_source(name_dq, '"', left, right))
    squote = bindings_from_text(f"{name_sq}='{left}\\'{right}'")
    print("runtime escapes", flush=True)
    assert require_binding(newline, name_n) == left + "\n" + right
    assert require_binding(dquote, name_dq) == left + '"' + right
    assert require_binding(squote, name_sq) == left + "'" + right


# ---------------------------------------------------------------------------
# E. Quoted values spanning lines
# ---------------------------------------------------------------------------


def test_double_quoted_real_newline_equals_escape_n():
    real = bindings_from_text('a="first line\nsecond line"')
    escaped = bindings_from_text('a="first line\\nsecond line"')
    print("double-quoted real newline vs \\n", flush=True)
    assert require_binding(real, "a") == require_binding(escaped, "a")
    assert require_binding(real, "a") == "first line\nsecond line"


def test_single_quoted_real_newline_spans_lines():
    mapping = bindings_from_text("a='first line\nsecond line'")
    print("single-quoted real newline", flush=True)
    assert require_binding(mapping, "a") == "first line\nsecond line"


def test_single_quoted_escape_n_not_equivalent():
    real = require_binding(bindings_from_text("a='first line\nsecond line'"), "a")
    escaped = require_binding(bindings_from_text("a='first line\\nsecond line'"), "a")
    print(f"single real={real!r} escaped={escaped!r}", flush=True)
    assert real != escaped
    assert escaped == "first line\\nsecond line"


def test_runtime_multiline_phrases():
    first, second, name = unique_token(), unique_token(), unique_token()
    real_double = bindings_from_text(f'{name}="{first}\n{second}"')
    esc_double = bindings_from_text(f'{name}="{first}\\n{second}"')
    real_single = bindings_from_text(f"{name}='{first}\n{second}'")
    esc_single = bindings_from_text(f"{name}='{first}\\n{second}'")
    print(f"runtime phrases {first!r} {second!r}", flush=True)
    assert require_binding(real_double, name) == require_binding(esc_double, name)
    assert require_binding(real_double, name) == first + "\n" + second
    assert require_binding(real_single, name) == first + "\n" + second
    assert require_binding(esc_single, name) == first + "\\n" + second
    assert require_binding(real_single, name) != require_binding(esc_single, name)


def test_binding_after_closed_multiline_value():
    later, later_value = unique_token(), unique_token()
    source = f'a="first line\nsecond line"\n{later}={later_value}'
    print(f"closed multiline then {later}", flush=True)
    mapping = bindings_from_text(source)
    assert require_binding(mapping, "a") == "first line\nsecond line"
    assert require_binding(mapping, later) == later_value


def test_multiline_quoted_interior_assignment_is_value_text():
    inner_name, inner_value = unique_token(), unique_token()
    inner = f"{inner_name}={inner_value}"
    outer, prefix, suffix = unique_token(), unique_token(), unique_token()
    double_src = f'{outer}="{prefix}\n{inner}\n{suffix}"'
    single_src = f"{outer}='{prefix}\n{inner}\n{suffix}'"
    print(f"interior assignment {inner!r}", flush=True)
    for source in (double_src, single_src):
        mapping = bindings_from_text(source)
        recorded = require_binding(mapping, outer)
        assert inner in recorded
        require_absent(mapping, inner_name)


# ---------------------------------------------------------------------------
# F. No-value vs empty string
# ---------------------------------------------------------------------------


def test_foo_without_equals_has_no_value():
    mapping = bindings_from_text("FOO")
    print("source FOO", flush=True)
    recorded = require_no_value(mapping, "FOO")
    assert "FOO" in mapping, (
        f"name-only FOO is absent (not a no-value binding); keys={list(mapping)!r}"
    )
    assert recorded != "", (
        f"name-only FOO recorded {recorded!r}, not no-value"
    )


def test_foo_equals_is_empty_string():
    mapping = bindings_from_text("FOO=")
    print("source FOO=", flush=True)
    recorded = require_empty_string(mapping, "FOO")
    assert "FOO" in mapping, (
        f"FOO= is absent; keys={list(mapping)!r}"
    )
    assert recorded == "", (
        f"FOO= recorded {recorded!r}, not the empty string"
    )

    name = unique_token()
    runtime = bindings_from_text(f"{name}=")
    print(f"runtime empty string {name!r}", flush=True)
    require_empty_string(runtime, name)


def test_no_value_empty_and_missing_are_distinct():
    no_value = bindings_from_text("FOO")
    empty = bindings_from_text("FOO=")
    missing_name = unique_token()
    print("three-way FOO / FOO= / missing", flush=True)
    require_no_value(no_value, "FOO")
    require_empty_string(empty, "FOO")
    require_absent(empty, missing_name)
    require_absent(no_value, missing_name)
    assert require_binding(no_value, "FOO") != require_binding(empty, "FOO")
    assert "FOO" in no_value
    assert "FOO" in empty
    assert missing_name not in empty


def test_runtime_no_value_vs_empty():
    name = unique_token()
    missing = unique_token()
    no_value = bindings_from_text(name)
    empty = bindings_from_text(f"{name}=")
    print(f"runtime three-way {name!r}", flush=True)
    require_no_value(no_value, name)
    require_empty_string(empty, name)
    require_absent(no_value, missing)
    require_absent(empty, missing)
    assert require_binding(no_value, name) != require_binding(empty, name)


def test_empty_string_is_not_an_error():
    later, later_value = unique_token(), unique_token()
    mapping = bindings_from_text(f"a=\n{later}={later_value}")
    print("a= then later binding", flush=True)
    require_empty_string(mapping, "a")
    assert require_binding(mapping, later) == later_value

    empty_name, later2, later2_value = unique_token(), unique_token(), unique_token()
    runtime = bindings_from_text(f"{empty_name}=\n{later2}={later2_value}")
    print(f"runtime empty then later {empty_name!r}", flush=True)
    require_empty_string(runtime, empty_name)
    assert require_binding(runtime, later2) == later2_value


# ---------------------------------------------------------------------------
# G. LF / CR / CRLF, BOM, Unicode, streams
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sep", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
def test_lf_cr_crlf_are_binding_separators(sep):
    mapping = bindings_from_text(f"a=b{sep}c=d")
    print(f"separator {sep!r}", flush=True)
    assert require_binding(mapping, "a") == "b"
    assert require_binding(mapping, "c") == "d"
    assert require_binding(mapping, "a") != "b" + sep + "c=d"


def test_runtime_pairs_split_on_cr():
    n1, v1, n2, v2 = unique_token(), unique_token(), unique_token(), unique_token()
    for sep, label in (("\n", "lf"), ("\r", "cr"), ("\r\n", "crlf")):
        forward = bindings_from_text(f"{n1}={v1}{sep}{n2}={v2}")
        swapped = bindings_from_text(f"{n2}={v2}{sep}{n1}={v1}")
        print(f"runtime pairs {label}", flush=True)
        assert require_binding(forward, n1) == v1
        assert require_binding(forward, n2) == v2
        assert require_binding(swapped, n2) == v2
        assert require_binding(swapped, n1) == v1


def test_blank_line_between_bindings():
    n1, v1, n2, v2 = unique_token(), unique_token(), unique_token(), unique_token()
    with_blank = bindings_from_text(f"{n1}={v1}\n\n{n2}={v2}")
    without = bindings_from_text(f"{n1}={v1}\n{n2}={v2}")
    print("blank line between bindings", flush=True)
    assert require_binding(with_blank, n1) == v1
    assert require_binding(with_blank, n2) == v2
    assert require_binding(without, n1) == v1
    assert require_binding(without, n2) == v2


def test_leading_bom_does_not_eat_first_name():
    with_bom = bindings_from_text("\ufeffa=b")
    without = bindings_from_text("a=b")
    print("stream BOM + a=b", flush=True)
    assert require_binding(with_bom, "a") == "b"
    assert require_binding(without, "a") == "b"
    require_absent(with_bom, "\ufeffa")

    with workspace() as ws:
        path = ws.write("bom.env", b"\xef\xbb\xbf" + b"a=b")
        from_file = bindings_from_file(path)
    print("file BOM bytes + a=b", flush=True)
    assert require_binding(from_file, "a") == "b"
    require_absent(from_file, "\ufeffa")

    name, value = unique_token(), unique_token()
    line = f"{name}={value}"
    runtime_bom = bindings_from_text("\ufeff" + line)
    print(f"public-test runtime BOM {name!r}", flush=True)
    assert require_binding(runtime_bom, name) == value
    require_absent(runtime_bom, "\ufeff" + name)


def test_leading_bom_ignored_on_runtime_binding():
    name, value = unique_token(), unique_token()
    with_bom = bindings_from_text("\ufeff" + f"{name}={value}")
    without = bindings_from_text(f"{name}={value}")
    print(f"runtime BOM {name!r}", flush=True)
    assert require_binding(with_bom, name) == value
    assert require_binding(without, name) == value
    require_absent(with_bom, "\ufeff" + name)


def test_unicode_value_preserved():
    unquoted = bindings_from_text("a=à")
    quoted = bindings_from_text('a="à"')
    print("unicode value à", flush=True)
    assert require_binding(unquoted, "a") == "à"
    assert require_binding(quoted, "a") == "à"

    name = unique_token()
    value = "à" + unique_token()
    runtime_unquoted = bindings_from_text(f"{name}={value}")
    runtime_quoted = bindings_from_text(f'{name}="{value}"')
    print(f"runtime unicode value {name!r}", flush=True)
    assert require_binding(runtime_unquoted, name) == value
    assert require_binding(runtime_quoted, name) == value


def test_file_decoded_as_utf8_when_encoding_not_named():
    name = unique_token()
    value = "à" + unique_token()
    with workspace() as ws:
        public_path = ws.write("public.env", "a=à".encode("utf-8"))
        runtime_path = ws.write("runtime.env", f"{name}={value}".encode("utf-8"))
        public = bindings_from_file(public_path)
        runtime = bindings_from_file(runtime_path)
    print("utf-8 file a=à without a named encoding", flush=True)
    assert require_binding(public, "a") == "à"
    print(f"utf-8 file {name!r} without a named encoding", flush=True)
    assert require_binding(runtime, name) == value


def test_file_written_as_utf8_when_encoding_not_named():
    name = unique_token()
    value = "à" + unique_token()
    with workspace() as ws:
        public_path = ws.resolve("public.env")
        runtime_path = ws.resolve("runtime.env")
        write_binding(public_path, "a", "à")
        write_binding(runtime_path, name, value)
        public_bytes = ws.read_bytes("public.env")
        runtime_bytes = ws.read_bytes("runtime.env")
    print("write a=à without a named encoding", flush=True)
    public_text = require_utf8_text(public_bytes, origin="unnamed-encoding write a=à")
    assert "à" in public_text
    print(f"write {name!r} without a named encoding", flush=True)
    runtime_text = require_utf8_text(
        runtime_bytes, origin=f"unnamed-encoding write {name!r}"
    )
    assert value in runtime_text


def test_unnamed_source_file_name_is_dotenv():
    pkg = product_package_name()
    name, value = unique_token(), unique_token()
    decoy_name, decoy_value = unique_token(), unique_token()
    with workspace() as ws:
        ws.write(".env", f"{name}={value}\n")
        ws.write("other.env", f"{decoy_name}={decoy_value}\n")
        result = ws.run_script(
            f"from {pkg} import envfile_values\n"
            "mapping = envfile_values(interpolate=False)\n"
            f"print('VALUE=' + mapping[{name!r}])\n"
            f"print('DECOY=' + ('yes' if {decoy_name!r} in mapping else 'no'))\n"
        )
    stdout = require_script_success(result, label="unnamed-source")
    assert require_labeled_line(stdout, "VALUE", origin="unnamed-source") == value
    assert require_labeled_line(stdout, "DECOY", origin="unnamed-source") == "no"


def test_unicode_name_preserved():
    name = "à" + unique_token()
    value = "é" + unique_token()
    mapping = bindings_from_text(f"{name}={value}")
    print(f"unicode name {name!r}", flush=True)
    assert require_binding(mapping, name) == value


def test_stream_and_file_same_bindings():
    name, value = unique_token(), unique_token()
    text = f"{name}={value}"
    from_stream = bindings_from_text(text)
    with workspace() as ws:
        path = ws.write("same.env", text)
        from_file = bindings_from_file(path)
    print(f"stream vs file {name!r}", flush=True)
    assert require_binding(from_stream, name) == value
    assert require_binding(from_file, name) == value
    assert require_binding(from_stream, name) == require_binding(from_file, name)


def test_dollar_brace_is_ordinary_text_without_expansion():
    token, filler, name = unique_token(), unique_token(), unique_token()
    brace = "${" + token + "}"
    source = f"{token}={filler}\n{name}={brace}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    assert require_binding(mapping, token) == filler
    recorded = require_binding(mapping, name)
    assert recorded == brace
    assert recorded != filler


# ---------------------------------------------------------------------------
# H. Invalid lines skipped; empty / YAML / JSON are not bindings
# ---------------------------------------------------------------------------


def test_colon_line_is_not_a_binding():
    token, value = unique_token(), unique_token()
    source = f"a: b\n{token}={value}"
    print(f"source {source!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, "a")
    assert require_binding(mapping, token) == value


def test_unclosed_double_quote_does_not_drop_later_line():
    mapping = bindings_from_text('a="\nb=c')
    print('source first line a=" then b=c', flush=True)
    require_absent(mapping, "a")
    assert require_binding(mapping, "b") == "c"


def test_runtime_unclosed_quote_skips_name():
    skipped, later, later_value = unique_token(), unique_token(), unique_token()
    source = skipped + '="\n' + f"{later}={later_value}"
    print(f"unclosed {skipped!r} then {later!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, skipped)
    assert require_binding(mapping, later) == later_value


def test_empty_source_yields_no_bindings():
    empty = bindings_from_text("")
    print(f"empty keys={list(empty)!r}", flush=True)
    assert list(empty) == []
    token, value = unique_token(), unique_token()
    baseline = bindings_from_text(f"{token}={value}")
    assert require_binding(baseline, token) == value


def test_blank_lines_yield_no_bindings():
    blank = bindings_from_text("\n\n  \n")
    print(f"blank keys={list(blank)!r}", flush=True)
    assert list(blank) == []
    token, value = unique_token(), unique_token()
    baseline = bindings_from_text(f"{token}={value}")
    assert require_binding(baseline, token) == value


def test_comment_only_yields_no_bindings():
    comments = bindings_from_text("# only\n# comments")
    print(f"comment-only keys={list(comments)!r}", flush=True)
    assert list(comments) == []
    token, value = unique_token(), unique_token()
    baseline = bindings_from_text(f"{token}={value}")
    assert require_binding(baseline, token) == value


def test_yaml_only_mapping_is_not_a_binding():
    source = "host:\n  name: example.org\n  port: 8000\n"
    print(f"yaml-only {source!r}", flush=True)
    mapping = bindings_from_text(source)
    require_absent(mapping, "host")
    require_absent(mapping, "name")
    require_absent(mapping, "port")

    token, value = unique_token(), unique_token()
    mixed = bindings_from_text(source + f"{token}={value}")
    print("yaml then later binding", flush=True)
    require_absent(mixed, "host")
    require_absent(mixed, "name")
    require_absent(mixed, "port")
    assert require_binding(mixed, token) == value


def test_json_only_object_is_not_a_binding():
    mapping = bindings_from_text('{"DOMAIN":"example.org"}')
    print('json-only {"DOMAIN":"example.org"}', flush=True)
    require_absent(mapping, "DOMAIN")

    token, value = unique_token(), unique_token()
    mixed = bindings_from_text('{"DOMAIN":"example.org"}\n' + f"{token}={value}")
    print("json then later binding", flush=True)
    require_absent(mixed, "DOMAIN")
    assert require_binding(mixed, token) == value


# ---------------------------------------------------------------------------
# I. Unix FIFO is a valid .env source for load
# ---------------------------------------------------------------------------


def test_fifo_load_my_password_pipe_secret():
    with workspace() as ws:
        with ws.fifo("pipe.env", "MY_PASSWORD=pipe-secret") as fifo:
            result = load_path(fifo)
    print("FIFO MY_PASSWORD=pipe-secret", flush=True)
    assert result.exception is None
    assert environ_value(result, "MY_PASSWORD") == "pipe-secret"


def test_runtime_fifo_binding_via_load():
    name, value = unique_token(), unique_token()
    content = f"{name}={value}"
    with workspace() as ws:
        with ws.fifo("runtime.fifo", content) as fifo:
            result = load_path(fifo)
    print(f"runtime FIFO {content!r}", flush=True)
    assert result.exception is None
    assert environ_value(result, name) == value


def test_fifo_and_regular_file_same_binding():
    name, value = unique_token(), unique_token()
    content = f"{name}={value}"
    with workspace() as ws:
        file_path = ws.write("regular.env", content)
        from_file = load_path(file_path)
        with ws.fifo("same.fifo", content) as fifo:
            from_fifo = load_path(fifo)
    print(f"FIFO vs file {name!r}", flush=True)
    assert from_file.exception is None
    assert from_fifo.exception is None
    assert environ_value(from_file, name) == value
    assert environ_value(from_fifo, name) == value


def test_fifo_is_valid_source_for_file_location():
    pkg = product_package_name()
    with workspace() as ws:
        with ws.fifo(".env", "MY_PASSWORD=pipe-secret") as fifo_path:
            result = ws.run_script(
                f"from {pkg} import envfile_values, find_envfile\n"
                "found = find_envfile()\n"
                "print('FOUND=' + found)\n"
                "envfile_values(envfile_path=found, interpolate=False)\n"
            )
            stdout = require_script_success(result, label="fifo-location")
            found = require_labeled_line(stdout, "FOUND", origin="fifo-location")
            assert found, "file location returned empty text for a FIFO source"
            assert Path(found).resolve() == Path(fifo_path).resolve()
            assert path_is_fifo(found), f"located path is not a FIFO: {found!r}"
            assert Path(found).name == ".env"


# ---------------------------------------------------------------------------
# J. Load from an in-memory stream
# ---------------------------------------------------------------------------


def test_probe_from_stream_writes_process_environment():
    result = load_text("PROBE=from_stream")
    print("load stream PROBE=from_stream", flush=True)
    assert result.exception is None
    assert environ_value(result, "PROBE") == "from_stream"
