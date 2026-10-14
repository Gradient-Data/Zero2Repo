# feature: F01
"""FP-01: parse TOML document structure from a Python text string.

Assertions follow the PRD FP-01 and the failure
carriers in FP-04. Nesting past the 470/310 depths of FP-01 is
unspecified and not asserted. Scalar fine
rules, the binary-file entry, and decode-error location text are later
feature points.
"""

from __future__ import annotations

from tomlparse import TOMLDecodeError, loads  # noqa: F401 — public string-parse surface

from F01_helpers import (
    dotted_key_source,
    is_mapping,
    is_sequence,
    nested_array_source,
    nested_inline_table_source,
    parse_text,
    require_decode_failure,
    require_mapping,
    require_nested_empty_except_chain,
    require_path,
    require_sequence_mappings_contain,
    require_sequence,
    require_str_keys,
    runtime_depth,
    runtime_int,
    runtime_token,
)

# ---------------------------------------------------------------------------
# Local observation (not product oracles)
# ---------------------------------------------------------------------------


def _is_int(obj: object) -> bool:
    return isinstance(obj, int) and not isinstance(obj, bool)


def _is_bool(obj: object) -> bool:
    return isinstance(obj, bool)


def _is_float(obj: object) -> bool:
    return isinstance(obj, float)


def _parse_mapping(source: str):
    print(f"parse source={source!r}", flush=True)
    return require_mapping(parse_text(source))


def _refuse(source: str):
    print(f"refuse source={source!r}", flush=True)
    return require_decode_failure(parse_text(source))


def _succeeds_near(source: str):
    print(f"neighbor source={source!r}", flush=True)
    return require_mapping(parse_text(source))


def _empty_with_baseline(empty_source: str):
    """Empty-document arm plus a live non-empty parse of the same entry."""
    empty = _parse_mapping(empty_source)
    assert len(empty) == 0, f"expected empty mapping, got {empty!r}"
    key = runtime_token()
    n = runtime_int()
    baseline = _parse_mapping(f"{key} = {n}")
    assert require_path(baseline, key) == n
    assert _is_int(require_path(baseline, key))
    return empty


def _walk_nested_sequence(root, depth: int):
    current = root
    for level in range(depth):
        seq = require_sequence(current)
        if level == depth - 1:
            assert len(seq) == 0, f"innermost sequence at depth {depth} is not empty"
            return seq
        assert len(seq) == 1, f"level {level} sequence length {len(seq)} != 1"
        current = seq[0]
    raise AssertionError("walk did not reach innermost sequence")


def _walk_nested_inline_tables(mapping, depth: int):
    current = mapping
    for _ in range(depth):
        if not is_mapping(current):
            raise AssertionError(f"expected nested mapping, got {type(current)!r}")
        require_str_keys(current)
        assert "key" in current, f"missing 'key' in {list(current)}"
        current = current["key"]
    if not is_mapping(current):
        raise AssertionError(f"innermost value is not a mapping: {type(current)!r}")
    assert len(current) == 0, f"innermost mapping is not empty: {current!r}"
    return current


def _walk_dotted_assignment(mapping, parts: int):
    current = mapping
    for _ in range(parts - 1):
        if not is_mapping(current):
            raise AssertionError(f"expected nested mapping, got {type(current)!r}")
        require_str_keys(current)
        assert "a" in current, f"missing 'a' in {list(current)}"
        current = current["a"]
    if not is_mapping(current):
        raise AssertionError(f"leaf parent is not a mapping: {type(current)!r}")
    assert current["a"] == 1
    assert _is_int(current["a"])
    return current["a"]


# ---------------------------------------------------------------------------
# S. Parse after install: name = "probe"
# ---------------------------------------------------------------------------


def test_probe_document_parses_when_package_importable():
    doc = _parse_mapping('name = "probe"')
    assert require_path(doc, "name") == "probe"
    assert isinstance(require_path(doc, "name"), str)


# ---------------------------------------------------------------------------
# A. Empty document and root pairs
# ---------------------------------------------------------------------------


def test_empty_text_is_empty_mapping():
    _empty_with_baseline("")


def test_whitespace_only_is_empty_mapping():
    _empty_with_baseline(" \t \n \t\n")


def test_comment_only_no_newline_is_empty_mapping():
    _empty_with_baseline("#no newlines at all here")
    _empty_with_baseline("# only comments here\n")


def test_runtime_comment_only_no_newline_is_empty_mapping():
    token = runtime_token()
    _empty_with_baseline("#" + token)


def test_one_two_arr_root_document():
    doc = _parse_mapping("one = 1\ntwo = 'two'\narr = []")
    assert require_path(doc, "one") == 1
    assert _is_int(require_path(doc, "one"))
    assert require_path(doc, "two") == "two"
    assert isinstance(require_path(doc, "two"), str)
    arr = require_sequence(require_path(doc, "arr"))
    assert len(arr) == 0


def test_runtime_root_pair():
    key = runtime_token()
    n = runtime_int()
    doc = _parse_mapping(f"{key} = {n}")
    assert set(doc) == {key}
    bound = require_path(doc, key)
    assert bound == n
    assert _is_int(bound)
    assert bound != str(n)


# ---------------------------------------------------------------------------
# B. Keys are strings
# ---------------------------------------------------------------------------


def test_bare_digit_key_is_string_not_int():
    doc = _parse_mapping("1234 = 1")
    assert "1234" in doc
    assert 1234 not in doc
    assert require_path(doc, "1234") == 1
    assert _is_int(require_path(doc, "1234"))


def test_hyphen_underscore_bare_keys_distinct():
    doc = _parse_mapping("bare_key = 1\nbare-key = 2\nbarekey = 3")
    assert require_path(doc, "bare_key") == 1
    assert require_path(doc, "bare-key") == 2
    assert require_path(doc, "barekey") == 3
    assert set(doc) >= {"bare_key", "bare-key", "barekey"}
    assert len({"bare_key", "bare-key", "barekey"}) == 3


def test_letter_case_distinct_for_keys_and_headers():
    doc = _parse_mapping("name = 1\nName = 2\n[section]\n[Section]\n")
    assert require_path(doc, "name") == 1
    assert require_path(doc, "Name") == 2
    assert is_mapping(require_path(doc, "section"))
    assert is_mapping(require_path(doc, "Section"))
    assert require_path(doc, "section") is not require_path(doc, "Name")


def test_true_false_inf_nan_are_valid_keys():
    src = (
        "false = false\n"
        "true = 1\n"
        "inf = 100000000\n"
        'nan = "ceci n\'est pas un nombre"\n'
    )
    doc = _parse_mapping(src)
    assert set(doc) == {"false", "true", "inf", "nan"}
    assert require_path(doc, "false") is False
    assert _is_bool(require_path(doc, "false"))
    assert require_path(doc, "true") == 1
    assert _is_int(require_path(doc, "true"))
    assert require_path(doc, "inf") == 100000000
    assert _is_int(require_path(doc, "inf"))
    assert require_path(doc, "nan") == "ceci n'est pas un nombre"
    assert isinstance(require_path(doc, "nan"), str)
    assert True not in doc
    assert False not in doc
    assert float("inf") not in doc


def test_empty_quoted_key():
    doc = _parse_mapping('"" = "blank"')
    assert require_path(doc, "") == "blank"
    assert isinstance(require_path(doc, ""), str)


def test_quoted_key_hash_spaces_dot_nonascii():
    src = (
        '"a b" = 2\n'
        '"Äpfel" = 3\n'
        '["key#group"]\n'
        "inner = 1\n"
    )
    doc = _parse_mapping(src)
    group = require_path(doc, "key#group")
    assert is_mapping(group)
    assert require_path(doc, "key#group", "inner") == 1
    assert require_path(doc, "a b") == 2
    assert require_path(doc, "Äpfel") == 3
    assert "key" not in doc


def test_quoted_dot_is_one_key_not_dotted():
    doc = _parse_mapping('"with.dot" = 1')
    assert "with.dot" in doc
    assert require_path(doc, "with.dot") == 1
    assert "with" not in doc


def test_runtime_keyword_looking_key_binds_integer():
    words = ("true", "false", "inf", "nan")
    word = words[runtime_int() % 4]
    n = runtime_int()
    doc = _parse_mapping(f"{word} = {n}")
    print(f"keyword-looking key {word!r} = {n}", flush=True)
    assert word in doc
    assert require_path(doc, word) == n
    assert _is_int(require_path(doc, word))


def test_runtime_all_digit_bare_key_is_string():
    n = runtime_int()
    while str(n) == "1234":
        n = runtime_int()
    doc = _parse_mapping(f"{n} = 1")
    print(f"digit key {n}", flush=True)
    assert str(n) in doc
    assert n not in doc
    assert require_path(doc, str(n)) == 1


def test_runtime_empty_quoted_key():
    value = runtime_token()
    doc = _parse_mapping(f'"" = "{value}"')
    assert "" in doc
    bound = require_path(doc, "")
    assert bound == value
    assert isinstance(bound, str)


def test_runtime_hyphen_underscore_glued_triplet():
    stem = runtime_token()
    hyphen = f"{stem}-a"
    under = f"{stem}_a"
    glued = f"{stem}a"
    src = f"{hyphen} = 1\n{under} = 2\n{glued} = 3\n"
    doc = _parse_mapping(src)
    assert require_path(doc, hyphen) == 1
    assert require_path(doc, under) == 2
    assert require_path(doc, glued) == 3
    assert hyphen != under != glued


def test_runtime_quoted_table_header_containing_hash():
    token = runtime_token()
    header = f"{token}#g"
    leaf = runtime_token()
    n = runtime_int()
    doc = _parse_mapping(f'["{header}"]\n{leaf} = {n}\n')
    table = require_path(doc, header)
    assert is_mapping(table)
    assert require_path(doc, header, leaf) == n
    assert token not in doc


def test_runtime_quoted_key_with_dot():
    token = runtime_token()
    key = f"{token}.x"
    n = runtime_int()
    doc = _parse_mapping(f'"{key}" = {n}')
    assert key in doc
    bound = require_path(doc, key)
    assert bound == n
    assert _is_int(bound)
    assert token not in doc


def test_runtime_literal_quoted_key():
    token = runtime_token()
    n = runtime_int()
    doc = _parse_mapping(f"'{token}' = {n}")
    bound = require_path(doc, token)
    assert bound == n
    assert _is_int(bound)
    assert bound != str(n)


# ---------------------------------------------------------------------------
# C. Dotted keys
# ---------------------------------------------------------------------------


def test_dotted_keys_nest_under_name():
    doc = _parse_mapping('name.first = "Arthur"\n"name".\'last\' = "Dent"\n')
    assert "name.first" not in doc
    assert require_path(doc, "name", "first") == "Arthur"
    assert require_path(doc, "name", "last") == "Dent"
    name = require_path(doc, "name")
    assert is_mapping(name)
    assert set(name) >= {"first", "last"}


def test_spaces_around_dots_ignored_in_pairs():
    compact = _parse_mapping("a.b = 1")
    spaced = _parse_mapping("a   .   b  =  1")
    assert len(compact) > 0 and len(spaced) > 0
    assert "a.b" not in compact
    assert "a.b" not in spaced
    assert require_path(compact, "a", "b") == 1
    assert require_path(spaced, "a", "b") == 1
    assert _is_int(require_path(compact, "a", "b"))
    assert _is_int(require_path(spaced, "a", "b"))
    assert compact == spaced


def test_spaces_around_dots_ignored_in_headers():
    compact = _parse_mapping("[g.h.i]\n")
    spaced = _parse_mapping("[ g . h . i ]\n")
    assert len(compact) > 0 and len(spaced) > 0
    inner_c = require_path(compact, "g", "h", "i")
    inner_s = require_path(spaced, "g", "h", "i")
    assert is_mapping(inner_c) and is_mapping(inner_s)
    assert len(inner_c) == 0 and len(inner_s) == 0
    assert compact == spaced


def test_runtime_spaces_around_dots_in_pairs():
    p, q = runtime_token(), runtime_token()
    n = runtime_int()
    compact = _parse_mapping(f"{p}.{q} = {n}")
    spaced = _parse_mapping(f"{p}  .    {q}  =  {n}")
    assert len(compact) > 0 and len(spaced) > 0
    assert f"{p}.{q}" not in compact
    assert f"{p}.{q}" not in spaced
    assert require_path(compact, p, q) == n
    assert require_path(spaced, p, q) == n
    assert _is_int(require_path(compact, p, q))
    assert _is_int(require_path(spaced, p, q))
    assert compact == spaced


def test_runtime_spaces_around_dots_in_headers():
    p, q = runtime_token(), runtime_token()
    compact = _parse_mapping(f"[{p}.{q}]\n")
    spaced = _parse_mapping(f"[  {p}  .  {q}  ]\n")
    assert len(compact) > 0 and len(spaced) > 0
    inner_c = require_path(compact, p, q)
    inner_s = require_path(spaced, p, q)
    assert is_mapping(inner_c) and is_mapping(inner_s)
    assert len(inner_c) == 0 and len(inner_s) == 0
    assert compact == spaced


def test_intermediate_table_accepts_more_dotted_keys():
    doc = _parse_mapping('apple.type = "fruit"\napple.color = "red"\n')
    apple = require_path(doc, "apple")
    assert is_mapping(apple)
    assert require_path(doc, "apple", "type") == "fruit"
    assert require_path(doc, "apple", "color") == "red"


def test_quoted_dot_vs_dotted_separator():
    dotted = _parse_mapping("with.dot = 1")
    quoted = _parse_mapping('"with.dot" = 1')
    assert require_path(dotted, "with", "dot") == 1
    assert "with.dot" not in dotted
    assert require_path(quoted, "with.dot") == 1
    assert "with" not in quoted
    assert dotted != quoted


def test_runtime_dotted_prefix_accumulates():
    prefix, leaf_a, leaf_b = runtime_token(), runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    src = f"{prefix}.{leaf_a} = {n}\n{prefix}.{leaf_b} = {m}\n"
    doc = _parse_mapping(src)
    mid = require_path(doc, prefix)
    assert is_mapping(mid)
    assert not is_sequence(mid)
    assert set(mid) == {leaf_a, leaf_b}
    assert require_path(doc, prefix, leaf_a) == n
    assert require_path(doc, prefix, leaf_b) == m
    assert _is_int(require_path(doc, prefix, leaf_a))
    assert _is_int(require_path(doc, prefix, leaf_b))
    assert f"{prefix}.{leaf_a}" not in doc
    assert f"{prefix}.{leaf_b}" not in doc


# ---------------------------------------------------------------------------
# D. Square-bracket headers
# ---------------------------------------------------------------------------


def test_header_opens_table_until_next_header():
    key_a, key_b = runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    other = runtime_token()
    src = f"[owner]\n{key_a} = {n}\n[{other}]\n{key_b} = {m}\n"
    doc = _parse_mapping(src)
    assert require_path(doc, "owner", key_a) == n
    assert require_path(doc, other, key_b) == m
    owner = require_path(doc, "owner")
    second = require_path(doc, other)
    assert key_b not in owner
    assert key_a not in second
    assert key_a not in doc
    assert key_b not in doc


def test_dotted_header_creates_parents():
    doc = _parse_mapping("[servers.alpha]\n")
    servers = require_path(doc, "servers")
    alpha = require_path(doc, "servers", "alpha")
    assert is_mapping(servers)
    assert is_mapping(alpha)


def test_omitted_super_table_then_later_super_header():
    doc = _parse_mapping("[x.y.z.w]\n")
    assert is_mapping(require_path(doc, "x"))
    assert is_mapping(require_path(doc, "x", "y"))
    assert is_mapping(require_path(doc, "x", "y", "z"))
    assert is_mapping(require_path(doc, "x", "y", "z", "w"))
    print(
        "omitted chain keys",
        [list(require_path(doc, *path)) for path in (("x",), ("x", "y"), ("x", "y", "z"), ("x", "y", "z", "w"))],
        flush=True,
    )
    require_nested_empty_except_chain(doc, "x", "y", "z", "w")
    sibling = runtime_token()
    n = runtime_int()
    later = _parse_mapping(f"[x.y.z.w]\n[x]\n{sibling} = {n}\n")
    assert require_path(later, "x", sibling) == n
    assert is_mapping(require_path(later, "x", "y", "z", "w"))
    assert sibling not in require_path(later, "x", "y")


def test_new_subtable_after_dotted_keys_fruit_apple_texture():
    src = (
        "[fruit]\n"
        'apple.color = "red"\n'
        "apple.taste.sweet = true\n"
        "[fruit.apple.texture]\n"
        "smooth = true\n"
    )
    doc = _parse_mapping(src)
    apple = require_path(doc, "fruit", "apple")
    assert is_mapping(apple)
    assert set(apple) >= {"color", "taste", "texture"}
    assert require_path(doc, "fruit", "apple", "color") == "red"
    assert require_path(doc, "fruit", "apple", "taste", "sweet") is True
    assert require_path(doc, "fruit", "apple", "texture", "smooth") is True


def test_runtime_new_subtable_after_dotted_keys():
    root, mid, leaf, sub, inner = (
        runtime_token(),
        runtime_token(),
        runtime_token(),
        runtime_token(),
        runtime_token(),
    )
    n = runtime_int()
    src = (
        f"[{root}]\n"
        f"{mid}.{leaf} = {n}\n"
        f"[{root}.{mid}.{sub}]\n"
        f"{inner} = true\n"
    )
    doc = _parse_mapping(src)
    middle = require_path(doc, root, mid)
    assert is_mapping(middle)
    assert not is_sequence(middle)
    assert require_path(doc, root, mid, leaf) == n
    assert _is_int(require_path(doc, root, mid, leaf))
    inner_val = require_path(doc, root, mid, sub, inner)
    assert inner_val is True
    assert _is_bool(inner_val)
    assert set(middle) >= {leaf, sub}
    assert is_mapping(require_path(doc, root, mid, sub))


def test_runtime_omitted_super_then_sibling():
    a, b, c, sib = (
        runtime_token(),
        runtime_token(),
        runtime_token(),
        runtime_token(),
    )
    n = runtime_int()
    omitted = _parse_mapping(f"[{a}.{b}.{c}]\n")
    print(
        "runtime omitted chain keys",
        [list(require_path(omitted, *path)) for path in ((a,), (a, b), (a, b, c))],
        flush=True,
    )
    require_nested_empty_except_chain(omitted, a, b, c)
    src = f"[{a}.{b}.{c}]\n[{a}]\n{sib} = {n}\n"
    doc = _parse_mapping(src)
    assert is_mapping(require_path(doc, a, b, c))
    assert require_path(doc, a, sib) == n
    assert sib not in require_path(doc, a, b)


# ---------------------------------------------------------------------------
# E. Arrays of tables
# ---------------------------------------------------------------------------


def test_two_players_append():
    src = (
        "[[players]]\n"
        'name = "Lehtinen"\n'
        "number = 26\n"
        "[[players]]\n"
        'name = "Numminen"\n'
        "number = 27\n"
    )
    doc = _parse_mapping(src)
    players = require_sequence(require_path(doc, "players"))
    assert len(players) == 2
    first, second = players[0], players[1]
    assert is_mapping(first) and is_mapping(second)
    assert require_path(first, "name") == "Lehtinen"
    assert require_path(first, "number") == 26
    assert _is_int(require_path(first, "number"))
    assert require_path(second, "name") == "Numminen"
    assert require_path(second, "number") == 27


def test_runtime_array_of_tables_appends():
    table = runtime_token()
    key = runtime_token()
    vals = [runtime_int(), runtime_int(), runtime_int()]
    src = "".join(f"[[{table}]]\n{key} = {v}\n" for v in vals)
    doc = _parse_mapping(src)
    items = require_sequence(require_path(doc, table))
    assert len(items) == 3
    for item, v in zip(items, vals):
        assert is_mapping(item)
        assert require_path(item, key) == v


def test_nested_aot_attaches_to_most_recent_parent():
    songs = [runtime_token() for _ in range(4)]
    src = (
        "[[albums]]\n"
        "[[albums.songs]]\n"
        f'name = "{songs[0]}"\n'
        "[[albums.songs]]\n"
        f'name = "{songs[1]}"\n'
        "[[albums]]\n"
        "[[albums.songs]]\n"
        f'name = "{songs[2]}"\n'
        "[[albums.songs]]\n"
        f'name = "{songs[3]}"\n'
    )
    doc = _parse_mapping(src)
    albums = require_sequence(require_path(doc, "albums"))
    assert len(albums) == 2
    first_songs = require_sequence(require_path(albums[0], "songs"))
    second_songs = require_sequence(require_path(albums[1], "songs"))
    assert len(first_songs) == 2
    assert len(second_songs) == 2
    assert require_path(first_songs[0], "name") == songs[0]
    assert require_path(first_songs[1], "name") == songs[1]
    assert require_path(second_songs[0], "name") == songs[2]
    assert require_path(second_songs[1], "name") == songs[3]


def test_later_single_bracket_attaches_to_current_aot_item():
    src = (
        "[[arr]]\n"
        "[arr.subtab]\n"
        "val = 1\n"
        "[[arr]]\n"
        "[arr.subtab]\n"
        "val = 2\n"
    )
    doc = _parse_mapping(src)
    items = require_sequence(require_path(doc, "arr"))
    assert len(items) == 2
    require_sequence_mappings_contain(items, "subtab")
    first_sub = require_path(items[0], "subtab")
    second_sub = require_path(items[1], "subtab")
    assert is_mapping(first_sub) and is_mapping(second_sub)
    assert require_path(first_sub, "val") == 1
    assert _is_int(require_path(first_sub, "val"))
    assert require_path(second_sub, "val") == 2
    assert _is_int(require_path(second_sub, "val"))


def test_runtime_later_single_bracket_attaches_to_current_aot_item():
    arr, sub, leaf = runtime_token(), runtime_token(), runtime_token()
    n1, n2 = runtime_int(), runtime_int()
    src = (
        f"[[{arr}]]\n"
        f"[{arr}.{sub}]\n"
        f"{leaf} = {n1}\n"
        f"[[{arr}]]\n"
        f"[{arr}.{sub}]\n"
        f"{leaf} = {n2}\n"
    )
    doc = _parse_mapping(src)
    items = require_sequence(require_path(doc, arr))
    assert len(items) == 2
    require_sequence_mappings_contain(items, sub)
    first_sub = require_path(items[0], sub)
    second_sub = require_path(items[1], sub)
    assert is_mapping(first_sub) and is_mapping(second_sub)
    assert require_path(first_sub, leaf) == n1
    assert _is_int(require_path(first_sub, leaf))
    assert require_path(second_sub, leaf) == n2
    assert _is_int(require_path(second_sub, leaf))


def test_implied_parent_of_dotted_aot_is_mapping():
    src = '[[albums.songs]]\nname = "Glory Days"\n'
    doc = _parse_mapping(src)
    albums = require_path(doc, "albums")
    assert is_mapping(albums)
    assert not is_sequence(albums)
    songs = require_sequence(require_path(doc, "albums", "songs"))
    assert len(songs) == 1
    assert require_path(songs[0], "name") == "Glory Days"


def test_explicit_aot_parent_is_sequence():
    implied = _parse_mapping('[[albums.songs]]\nname = "Glory Days"\n')
    explicit = _parse_mapping('[[albums]]\n[[albums.songs]]\nname = "Glory Days"\n')
    implied_albums = require_path(implied, "albums")
    explicit_albums = require_path(explicit, "albums")
    assert is_mapping(implied_albums)
    assert not is_sequence(implied_albums)
    assert is_sequence(explicit_albums)
    assert not is_mapping(explicit_albums)
    implied_kind = (is_mapping(implied_albums), is_sequence(implied_albums))
    explicit_kind = (is_mapping(explicit_albums), is_sequence(explicit_albums))
    assert implied_kind != explicit_kind


def test_runtime_implied_parent_mapping_vs_explicit_sequence():
    parent, child, leaf = runtime_token(), runtime_token(), runtime_token()
    n = runtime_int()
    implied = _parse_mapping(f"[[{parent}.{child}]]\n{leaf} = {n}\n")
    explicit = _parse_mapping(f"[[{parent}]]\n[[{parent}.{child}]]\n{leaf} = {n}\n")
    implied_parent = require_path(implied, parent)
    explicit_parent = require_path(explicit, parent)
    assert is_mapping(implied_parent) and not is_sequence(implied_parent)
    assert is_sequence(explicit_parent) and not is_mapping(explicit_parent)
    implied_kind = (is_mapping(implied_parent), is_sequence(implied_parent))
    explicit_kind = (is_mapping(explicit_parent), is_sequence(explicit_parent))
    assert implied_kind != explicit_kind
    implied_child = require_sequence(require_path(implied, parent, child))
    assert len(implied_child) == 1
    assert require_path(implied_child[0], leaf) == n
    assert _is_int(require_path(implied_child[0], leaf))
    explicit_first = explicit_parent[0]
    assert is_mapping(explicit_first)
    explicit_child = require_sequence(require_path(explicit_first, child))
    assert len(explicit_child) == 1
    assert require_path(explicit_child[0], leaf) == n
    assert _is_int(require_path(explicit_child[0], leaf))


def test_later_parent_header_adds_sibling_after_aot():
    doc = _parse_mapping("[[a.b]]\nx = 1\n[a]\ny = 2\n")
    a = require_path(doc, "a")
    assert is_mapping(a)
    assert is_sequence(require_path(doc, "a", "b"))
    assert require_path(doc, "a", "y") == 2
    items = require_sequence(require_path(doc, "a", "b"))
    assert len(items) == 1
    assert require_path(items[0], "x") == 1


def test_parent_table_header_adds_non_arr_sibling():
    public = _parse_mapping("[[parent-table.arr]]\n[parent-table]\nnot-arr = 1\n")
    parent = require_path(public, "parent-table")
    assert is_mapping(parent)
    assert is_sequence(require_path(public, "parent-table", "arr"))
    assert require_path(public, "parent-table", "not-arr") == 1

    table, arr, sib = runtime_token(), runtime_token(), runtime_token()
    n = runtime_int()
    runtime = _parse_mapping(f"[[{table}.{arr}]]\n[{table}]\n{sib} = {n}\n")
    assert is_sequence(require_path(runtime, table, arr))
    assert require_path(runtime, table, sib) == n
    assert sib != arr


def test_dotted_key_into_aot_is_refused():
    bad = "[[tab.arr]]\n[tab]\narr.val1 = 1\n"
    _refuse(bad)
    neighbor = _succeeds_near("[[tab.arr]]\n[tab]\nnot-arr = 1\n")
    assert is_sequence(require_path(neighbor, "tab", "arr"))
    assert require_path(neighbor, "tab", "not-arr") == 1


def test_runtime_dotted_key_into_aot_is_refused():
    table, arr, leaf = runtime_token(), runtime_token(), runtime_token()
    sib = runtime_token()
    n = runtime_int()
    _refuse(f"[[{table}.{arr}]]\n[{table}]\n{arr}.{leaf} = {n}\n")
    neighbor = _succeeds_near(f"[[{table}.{arr}]]\n[{table}]\n{sib} = {n}\n")
    assert is_sequence(require_path(neighbor, table, arr))
    assert require_path(neighbor, table, sib) == n


# ---------------------------------------------------------------------------
# F. Inline tables
# ---------------------------------------------------------------------------


def test_inline_table_point_xy():
    doc = _parse_mapping("point = { x = 1, y = 2 }")
    point = require_path(doc, "point")
    assert is_mapping(point)
    assert require_path(doc, "point", "x") == 1
    assert require_path(doc, "point", "y") == 2
    assert _is_int(require_path(doc, "point", "x"))
    assert _is_int(require_path(doc, "point", "y"))


def test_empty_inline_table():
    doc = _parse_mapping("empty = { }")
    empty = require_path(doc, "empty")
    assert is_mapping(empty)
    assert len(empty) == 0


def test_runtime_empty_inline_table():
    key = runtime_token()
    doc = _parse_mapping(f"{key} = {{  }}")
    empty = require_path(doc, key)
    assert is_mapping(empty)
    assert not is_sequence(empty)
    assert len(empty) == 0


def test_dotted_key_inside_inline_table():
    doc = _parse_mapping("t = { a.b = 1 }")
    assert is_mapping(require_path(doc, "t", "a"))
    assert require_path(doc, "t", "a", "b") == 1


def test_runtime_dotted_key_inside_inline_table():
    key, p, q = runtime_token(), runtime_token(), runtime_token()
    n = runtime_int()
    doc = _parse_mapping(f"{key} = {{ {p}.{q} = {n} }}")
    assert is_mapping(require_path(doc, key, p))
    assert require_path(doc, key, p, q) == n


def test_inline_table_trailing_comma():
    doc = _parse_mapping("t = { c = 1, }")
    table = require_path(doc, "t")
    assert is_mapping(table)
    assert require_path(doc, "t", "c") == 1
    assert set(table) == {"c"}


def test_inline_table_multiline_and_comments():
    src = "t = {\nc = 1,\n}\n"
    doc = _parse_mapping(src)
    table = require_path(doc, "t")
    assert is_mapping(table)
    assert require_path(doc, "t", "c") == 1
    assert set(table) == {"c"}


def test_inline_table_comment_after_closing_brace():
    doc = _parse_mapping("t = { c = 1, }#comment")
    table = require_path(doc, "t")
    assert is_mapping(table)
    assert require_path(doc, "t", "c") == 1
    assert "comment" not in table
    assert "comment" not in doc


def test_runtime_inline_comments_after_brace_and_comma():
    key, inner, note = runtime_token(), runtime_token(), runtime_token()
    n = runtime_int()
    src = f"{key} = {{ #{note}\n{inner} = {n}, #{note}\n}}\n"
    doc = _parse_mapping(src)
    table = require_path(doc, key)
    assert is_mapping(table)
    assert require_path(doc, key, inner) == n
    assert note not in table
    assert note not in doc


def test_runtime_inline_table_v11_newlines():
    key, inner = runtime_token(), runtime_token()
    n = runtime_int()
    src = f"{key} = {{\n{inner} = {n},\n}}\n"
    doc = _parse_mapping(src)
    table = require_path(doc, key)
    assert is_mapping(table)
    assert require_path(doc, key, inner) == n
    assert set(table) == {inner}


# ---------------------------------------------------------------------------
# G. Arrays
# ---------------------------------------------------------------------------


def test_empty_array():
    doc = _parse_mapping("arr = []")
    arr = require_sequence(require_path(doc, "arr"))
    assert len(arr) == 0


def test_mixed_int_float_array():
    doc = _parse_mapping("arr = [1, 1.1]")
    arr = require_sequence(require_path(doc, "arr"))
    assert len(arr) == 2
    assert arr[0] == 1 and _is_int(arr[0])
    assert _is_float(arr[1])
    assert arr[1] == 1.1


def test_runtime_mixed_int_float_array():
    n = runtime_int()
    token = f"{n}.5"
    expected = n + 0.5
    key = runtime_token()
    doc = _parse_mapping(f"{key} = [{n}, {token}]")
    arr = require_sequence(require_path(doc, key))
    assert len(arr) == 2
    assert arr[0] == n and _is_int(arr[0])
    assert _is_float(arr[1])
    assert arr[1] == expected
    assert arr[1] != int(expected)
    assert not _is_int(arr[1])


def test_nested_arrays():
    doc = _parse_mapping('arr = [ ["gamma", "delta"], [1, 2] ]')
    arr = require_sequence(require_path(doc, "arr"))
    assert len(arr) == 2
    first = require_sequence(arr[0])
    second = require_sequence(arr[1])
    assert list(first) == ["gamma", "delta"]
    assert list(second) == [1, 2]
    assert _is_int(second[0]) and _is_int(second[1])


def test_runtime_nested_arrays():
    a, b, c, d = (runtime_token() for _ in range(4))
    key = runtime_token()
    src = f'{key} = [ ["{a}", "{b}"], ["{c}", "{d}"] ]'
    doc = _parse_mapping(src)
    arr = require_sequence(require_path(doc, key))
    assert len(arr) == 2
    first = require_sequence(arr[0])
    second = require_sequence(arr[1])
    assert len(first) == 2 and len(second) == 2
    assert list(first) == [a, b]
    assert list(second) == [c, d]
    assert list(arr) != [a, b, c, d]


def test_array_trailing_comma():
    doc = _parse_mapping("arr = [1,]")
    arr = require_sequence(require_path(doc, "arr"))
    assert list(arr) == [1]
    listed = _parse_mapping("arr = [1, 2,]")
    assert list(require_sequence(require_path(listed, "arr"))) == [1, 2]


def test_array_multiline_with_comments_between_elements():
    src = "arr = [\n1,\n# between\n2,\n]\n"
    doc = _parse_mapping(src)
    arr = require_sequence(require_path(doc, "arr"))
    assert list(arr) == [1, 2]
    assert "between" not in arr
    for item in arr:
        assert item != "between"


def test_runtime_array_order_and_comments():
    key, note = runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    src = f"{key} = [\n{n},\n# {note}\n{m},\n]\n"
    doc = _parse_mapping(src)
    arr = require_sequence(require_path(doc, key))
    assert list(arr) == [n, m]
    assert note not in arr
    assert len(arr) == 2


# ---------------------------------------------------------------------------
# H. Comments, indent, CRLF
# ---------------------------------------------------------------------------


def test_hash_inside_string_kept():
    doc = _parse_mapping('another = "# This is not a comment"')
    assert require_path(doc, "another") == "# This is not a comment"
    assert "This" not in doc


def test_runtime_hash_inside_string_kept():
    key, token = runtime_token(), runtime_token()
    doc = _parse_mapping(f'{key} = "#{token}"')
    value = require_path(doc, key)
    assert value == f"#{token}"
    assert isinstance(value, str)
    assert token not in doc


def test_glued_comment_after_boolean():
    doc = _parse_mapping("true=true#true")
    assert require_path(doc, "true") is True
    assert _is_bool(require_path(doc, "true"))
    assert set(doc) == {"true"}


def test_runtime_glued_comment_after_boolean():
    key, token = runtime_token(), runtime_token()
    doc = _parse_mapping(f"{key}=true#{token}")
    bound = require_path(doc, key)
    assert bound is True
    assert _is_bool(bound)
    assert token not in doc
    assert bound != token
    assert not isinstance(bound, str)
    assert set(doc) == {key}


def test_nonascii_comment_is_not_a_key():
    key = runtime_token()
    n = runtime_int()
    src = f"# café-注释\n{key} = {n}\n"
    doc = _parse_mapping(src)
    assert require_path(doc, key) == n
    assert "café-注释" not in doc
    assert "café" not in doc


def test_comment_after_header_aot_and_datetime():
    src = (
        "[hdr] # hdrword\n"
        "k = 1\n"
        "[[items]] # aotword\n"
        "when = 1979-05-27T07:32:00Z # dtword\n"
    )
    doc = _parse_mapping(src)
    assert is_mapping(require_path(doc, "hdr"))
    assert require_path(doc, "hdr", "k") == 1
    items = require_sequence(require_path(doc, "items"))
    assert len(items) == 1
    when = require_path(items[0], "when")
    assert "hdrword" not in doc
    assert "aotword" not in doc
    assert "dtword" not in doc
    assert "hdrword" not in items[0]
    assert "dtword" not in items[0]
    assert not isinstance(when, str) or "dtword" not in when


def test_space_or_tab_indent_ignored():
    plain = _parse_mapping("k = 1")
    spaced = _parse_mapping("  k = 1")
    tabbed = _parse_mapping("\tk = 1")
    assert require_path(plain, "k") == 1
    assert require_path(spaced, "k") == 1
    assert require_path(tabbed, "k") == 1
    assert plain == spaced == tabbed


def test_crlf_between_keys_is_one_separator():
    lf = _parse_mapping("a = 1\nb = 2\n")
    crlf = _parse_mapping("a = 1\r\nb = 2\r\n")
    assert require_path(lf, "a") == 1
    assert require_path(lf, "b") == 2
    assert require_path(crlf, "a") == 1
    assert require_path(crlf, "b") == 2
    assert lf == crlf
    assert "\r" not in "".join(crlf)
    assert "a\r" not in crlf


def test_crlf_inside_string_equals_lf():
    lf = _parse_mapping('s = """\nhello\nworld\n"""\n')
    crlf = _parse_mapping('s = """\r\nhello\r\nworld\r\n"""\n')
    lf_val = require_path(lf, "s")
    crlf_val = require_path(crlf, "s")
    assert isinstance(lf_val, str) and isinstance(crlf_val, str)
    assert lf_val == crlf_val
    assert "\r" not in crlf_val
    assert "hello" in crlf_val and "world" in crlf_val


# ---------------------------------------------------------------------------
# I. Structural refusal and nesting limits
# ---------------------------------------------------------------------------


def test_duplicate_key_refused():
    _refuse("a = 1\na = 2\n")
    neighbor = _succeeds_near("a = 1\n")
    assert require_path(neighbor, "a") == 1


def test_duplicate_table_header_refused():
    _refuse("[table]\n[table]\n")
    neighbor = _succeeds_near("[table]\nk = 1\n")
    assert require_path(neighbor, "table", "k") == 1


def test_duplicate_key_in_inline_table_refused():
    _refuse("t = { a = 1, a = 2 }")
    neighbor = _succeeds_near("t = { a = 1 }")
    assert require_path(neighbor, "t", "a") == 1


def test_reopen_via_dotted_after_header_refused():
    _refuse("[a.b.c]\nz = 9\n[a]\nb.c.t = 9\n")
    neighbor = _succeeds_near("[a.b.c]\nz = 9\n")
    assert require_path(neighbor, "a", "b", "c", "z") == 9


def test_reopen_t1_t2_header_refused():
    _refuse("[t1]\nt2.t3.v = 0\n[t1.t2]\n")
    neighbor = _succeeds_near("[t1]\nt2.t3.v = 0\n")
    assert require_path(neighbor, "t1", "t2", "t3", "v") == 0


def test_reopen_fruit_apple_header_refused():
    _refuse("[fruit]\napple.color = \"red\"\n[fruit.apple]\n")
    neighbor = _succeeds_near("[fruit]\napple.color = \"red\"\n")
    assert require_path(neighbor, "fruit", "apple", "color") == "red"


def test_value_overwritten_by_table_header_refused():
    _refuse("a = 1\n[a.b.c.d]\n")
    neighbor = _succeeds_near("a = 1\n")
    assert require_path(neighbor, "a") == 1


def test_value_overwritten_by_aot_header_refused():
    _refuse("a = true\n[[a]]\n")
    neighbor = _succeeds_near("a = true\n")
    assert require_path(neighbor, "a") is True


def test_inline_table_mutation_refused():
    _refuse("a = { b = 1 }\na.b = 2\n")
    neighbor = _succeeds_near("a = { b = 1 }\n")
    assert require_path(neighbor, "a", "b") == 1


def test_missing_value_refused():
    _refuse("key =\n")
    _refuse("key = # comment only\n")
    neighbor = _succeeds_near("key = 1\n")
    assert require_path(neighbor, "key") == 1


def test_equals_without_key_refused():
    _refuse("= 1\n")
    neighbor = _succeeds_near("k = 1\n")
    assert require_path(neighbor, "k") == 1


def test_multiline_string_key_refused():
    _refuse('"""key""" = 1\n')
    neighbor = _succeeds_near('"key" = 1\n')
    assert require_path(neighbor, "key") == 1


def test_multiline_string_table_name_refused():
    _refuse('["""tbl"""]\nk = 1\n')
    neighbor = _succeeds_near('["tbl"]\nk = 1\n')
    assert require_path(neighbor, "tbl", "k") == 1


def test_header_spanning_lines_refused():
    _refuse("[tbl\n]\nk = 1\n")
    neighbor = _succeeds_near("[tbl]\nk = 1\n")
    assert require_path(neighbor, "tbl", "k") == 1


def test_header_sharing_line_with_pair_refused():
    _refuse("[tbl] k = 1\n")
    neighbor = _succeeds_near("[tbl]\nk = 1\n")
    assert require_path(neighbor, "tbl", "k") == 1


def test_runtime_duplicate_key_refused():
    key = runtime_token()
    n, m = runtime_int(), runtime_int()
    _refuse(f"{key} = {n}\n{key} = {m}\n")
    neighbor = _succeeds_near(f"{key} = {n}\n")
    assert require_path(neighbor, key) == n


def test_runtime_duplicate_key_under_header_table_refused():
    hdr, key = runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    _refuse(f"[{hdr}]\n{key} = {n}\n{key} = {m}\n")
    neighbor = _succeeds_near(f"[{hdr}]\n{key} = {n}\n")
    assert require_path(neighbor, hdr, key) == n


def test_runtime_duplicate_table_header_refused():
    hdr = runtime_token()
    _refuse(f"[{hdr}]\n[{hdr}]\n")
    neighbor = _succeeds_near(f"[{hdr}]\n")
    assert is_mapping(require_path(neighbor, hdr))


def test_runtime_duplicate_inline_key_refused():
    outer, inner = runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    _refuse(f"{outer} = {{ {inner} = {n}, {inner} = {m} }}")
    neighbor = _succeeds_near(f"{outer} = {{ {inner} = {n} }}")
    assert require_path(neighbor, outer, inner) == n


def test_runtime_reopen_header_opened_table_refused():
    root, mid, leaf = runtime_token(), runtime_token(), runtime_token()
    n = runtime_int()
    _refuse(f"[{root}]\n{mid}.{leaf} = {n}\n[{root}.{mid}]\n")
    neighbor = _succeeds_near(f"[{root}]\n{mid}.{leaf} = {n}\n")
    assert require_path(neighbor, root, mid, leaf) == n


def test_runtime_value_overwritten_by_table_header_refused():
    val = runtime_token()
    n = runtime_int()
    _refuse(f"{val} = {n}\n[{val}.x.y]\n")
    neighbor = _succeeds_near(f"{val} = {n}\n")
    assert require_path(neighbor, val) == n


def test_runtime_value_overwritten_by_aot_header_refused():
    val = runtime_token()
    _refuse(f"{val} = true\n[[{val}]]\n")
    neighbor = _succeeds_near(f"{val} = true\n")
    assert require_path(neighbor, val) is True


def test_runtime_inline_table_mutation_refused():
    key, inner = runtime_token(), runtime_token()
    n, m = runtime_int(), runtime_int()
    _refuse(f"{key} = {{ {inner} = {n} }}\n{key}.{inner} = {m}\n")
    neighbor = _succeeds_near(f"{key} = {{ {inner} = {n} }}\n")
    assert require_path(neighbor, key, inner) == n


def test_runtime_missing_value_refused():
    key, note = runtime_token(), runtime_token()
    _refuse(f"{key} = #{note}\n")
    neighbor = _succeeds_near(f"{key} = 1\n")
    assert require_path(neighbor, key) == 1


def test_runtime_equals_without_key_refused():
    n = runtime_int()
    _refuse(f"= {n}\n")
    neighbor = _succeeds_near(f"k = {n}\n")
    assert require_path(neighbor, "k") == n


def test_runtime_multiline_string_key_refused():
    token = runtime_token()
    _refuse(f'"""{token}""" = 1\n')
    neighbor = _succeeds_near(f'"{token}" = 1\n')
    assert require_path(neighbor, token) == 1


def test_runtime_multiline_literal_key_refused():
    token = runtime_token()
    _refuse(f"'''{token}''' = 1\n")
    neighbor = _succeeds_near(f"'{token}' = 1\n")
    assert require_path(neighbor, token) == 1


def test_runtime_multiline_literal_table_name_refused():
    token = runtime_token()
    _refuse(f"['''{token}''']\nk = 1\n")
    neighbor = _succeeds_near(f"['{token}']\nk = 1\n")
    assert require_path(neighbor, token, "k") == 1


def test_runtime_header_spanning_lines_refused():
    hdr, key = runtime_token(), runtime_token()
    n = runtime_int()
    _refuse(f"[{hdr}\n]\n{key} = {n}\n")
    neighbor = _succeeds_near(f"[{hdr}]\n{key} = {n}\n")
    assert require_path(neighbor, hdr, key) == n


def test_runtime_header_sharing_line_with_pair_refused():
    hdr, key = runtime_token(), runtime_token()
    n = runtime_int()
    _refuse(f"[{hdr}] {key} = {n}\n")
    neighbor = _succeeds_near(f"[{hdr}]\n{key} = {n}\n")
    assert require_path(neighbor, hdr, key) == n


def test_inline_array_nested_470_succeeds():
    src = nested_array_source(470)
    print(f"nested array depth=470 len={len(src)}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_nested_sequence(require_path(doc, "arr"), 470)


def test_inline_table_nested_310_succeeds():
    src = nested_inline_table_source(310)
    print(f"nested inline table depth=310 len={len(src)}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_nested_inline_tables(doc, 310)


def test_dotted_key_310_parts_succeeds():
    src = dotted_key_source(310)
    print(f"dotted key parts=310 src_prefix={src[:40]!r}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_dotted_assignment(doc, 310)


def test_runtime_intermediate_nested_array_succeeds():
    depth = runtime_depth()
    key = runtime_token()
    src = f"{key} = " + "[" * depth + "]" * depth
    print(f"intermediate nested array depth={depth} key={key}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_nested_sequence(require_path(doc, key), depth)


def test_runtime_intermediate_nested_inline_table_succeeds():
    depth = runtime_depth()
    src = nested_inline_table_source(depth)
    print(f"intermediate nested inline table depth={depth}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_nested_inline_tables(doc, depth)


def test_runtime_intermediate_dotted_key_succeeds():
    depth = runtime_depth()
    src = dotted_key_source(depth)
    print(f"intermediate dotted key parts={depth}", flush=True)
    doc = require_mapping(parse_text(src))
    _walk_dotted_assignment(doc, depth)


def test_stated_nesting_depths_all_yield_mappings():
    """The FP-01 depths (470 nested arrays, 310 nested inline tables, 310
    dotted parts) each yield a mapping. Deeper input is unspecified and is
    not exercised.
    """
    print("lower bounds: array=470 inline-table=310 dotted=310", flush=True)
    array_doc = require_mapping(parse_text(nested_array_source(470)))
    _walk_nested_sequence(require_path(array_doc, "arr"), 470)
    table_doc = require_mapping(parse_text(nested_inline_table_source(310)))
    _walk_nested_inline_tables(table_doc, 310)
    dotted_doc = require_mapping(parse_text(dotted_key_source(310)))
    _walk_dotted_assignment(dotted_doc, 310)
