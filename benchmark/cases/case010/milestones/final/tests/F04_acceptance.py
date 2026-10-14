# feature: F04
"""Chunking (FP-04).

Caller-written clause names are the chunk labels. Root / person-chunk
spellings are not pinned. Missing-resource refusals are distinguished
from a rooted chunk structure (including an empty tree). Exception
types and message wording are not pinned.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

from lingora.chunk import RegexpParser, ne_chunk
from lingora.tag import pos_tag

from _harness import call, workspace
from _helpers import (
    assert_chunk_covers,
    assert_direct_leaf,
    assert_leaves_equal,
    bound_resource_path,
    chunk_children,
    chunk_leaves,
    chunked_of,
    containing_chunks,
    install_perceptron,
    is_chunk_node,
    is_tagged_leaf,
    node_label,
    pairing_token,
    require_chunking_unsuccessful,
    require_grammar_refused,
    tag_value,
    tagged_of,
)

LANG_ENG = "eng"

THE_BIG_DOG = [
    ("the", "DT"),
    ("big", "JJ"),
    ("dog", "NN"),
    ("barked", "VBD"),
]
DOG_BARKED = [("dog", "NN"), ("barked", "VBD")]
BARKED_ALONE = [("barked", "VBD")]
THE_DOG_BARKED = [("the", "DT"), ("dog", "NN"), ("barked", "VBD")]
THE_BIG_BARKED = [("the", "DT"), ("big", "JJ"), ("barked", "VBD")]

LITTLE_CAT = [
    ("the", "DT"),
    ("little", "JJ"),
    ("cat", "NN"),
    ("sat", "VBD"),
    ("on", "IN"),
    ("the", "DT"),
    ("mat", "NN"),
]

COURT_FOUR = [
    ("Court", "NN-TL"),
    ("Judge", "NN-TL"),
    ("Durwood", "NP"),
    ("Pye", "NP"),
]
TERM_JURY = [("term", "NN"), ("jury", "NN")]
MAYOR_FOUR = [
    ("Mayor-nominate", "NN-TL"),
    ("Ivan", "NP"),
    ("Allen", "NP"),
    ("Jr.", "NP"),
]

HOMEPAGE = [
    "At",
    "eight",
    "o'clock",
    "on",
    "Thursday",
    "morning",
    "Arthur",
    "did",
    "n't",
    "feel",
    "very",
    "good",
    ".",
]

NP_PATTERN = "{<DT>?<JJ>*<NN>}"
# Spaces sit between complete tag groups, not next to ? / * as regex
# quantifiers of whitespace. If whitespace were kept, those spaces would
# have to match between tags; L30 says they are ignored.
NP_PATTERN_SPACED = "{<DT>? <JJ>* <NN>}"
N4_PATTERN = "{<N.*>{4,}}"
EVERYTHING_PATTERN = "{<.*>+}"
CHINK_VBD_IN = "}<VBD|IN>+{"
VBD_PATTERN = "{<VBD>}"

_PUBLIC_TAGS = {"DT", "JJ", "NN", "VBD", "IN", "NP", "NN-TL", "VB", "NNP"}
_PUBLIC_TOKENS = {
    "the",
    "big",
    "dog",
    "barked",
    "little",
    "cat",
    "sat",
    "on",
    "mat",
    "Court",
    "Judge",
    "Durwood",
    "Pye",
    "term",
    "jury",
    "Mayor-nominate",
    "Ivan",
    "Allen",
    "Jr.",
    "Arthur",
    "Thursday",
    "morning",
}


def _runtime_token(*, forbidden: set[str] | None = None) -> str:
    blocked = set(forbidden or ())
    blocked.update(_PUBLIC_TOKENS)
    while True:
        tok = "w" + uuid.uuid4().hex[:8]
        if tok not in blocked:
            return tok


def _runtime_label(*, forbidden: set[str] | None = None) -> str:
    blocked = set(forbidden or ())
    blocked.update({"NP", "S", "PERSON", "VP", "PP", "O"})
    while True:
        lab = "C" + uuid.uuid4().hex[:6].upper()
        if lab not in blocked:
            return lab


def _runtime_tag(*, forbidden: set[str] | None = None) -> str:
    blocked = set(forbidden or ())
    blocked.update(_PUBLIC_TAGS)
    while True:
        tag = "Z" + uuid.uuid4().hex[:6].upper()
        if tag not in blocked and not tag.startswith("N"):
            return tag


def _runtime_n_tag() -> str:
    blocked = {"NN", "NP", "NN-TL"}
    while True:
        tag = "NX" + uuid.uuid4().hex[:4].upper()
        if tag not in blocked:
            return tag


def _clause(label: str, *patterns: str) -> str:
    lines = [f"{label}: {patterns[0]}"]
    for pattern in patterns[1:]:
        lines.append(f"    {pattern}")
    return "\n".join(lines)


def _np_grammar(label: str) -> str:
    return _clause(label, NP_PATTERN)


def _labelled_spans(tree, label: str) -> list[list[tuple[object, str]]]:
    spans: list[list[tuple[object, str]]] = []

    def walk(node, is_root: bool) -> None:
        if is_tagged_leaf(node):
            return
        if not is_chunk_node(node):
            raise AssertionError(
                f"unclassifiable node while listing {label!r} chunks: {node!r}"
            )
        if not is_root and node_label(node) == label:
            spans.append(
                [(pairing_token(leaf), tag_value(leaf)) for leaf in chunk_leaves(node)]
            )
        for child in chunk_children(node):
            walk(child, False)

    walk(tree, True)
    return spans


def _keys(tagged) -> list[tuple[object, str]]:
    return [(pairing_token(pair), tag_value(pair)) for pair in tagged]


@contextmanager
def _empty_resources():
    """No packaged models on the search list (regular-expression chunking)."""
    with workspace() as ws:
        with bound_resource_path(ws, present=False):
            yield ws


@contextmanager
def _perceptron_without_ne():
    """English perceptron only — named-entity tree is not installed."""
    with workspace() as ws:
        install_perceptron(ws, LANG_ENG)
        with bound_resource_path(ws, present=True):
            yield ws


def _assert_np_then_vbd_leaf(tree, tagged, label: str) -> None:
    assert_chunk_covers(tree, tagged[:3], label)
    assert_direct_leaf(tree, tagged[3])
    spans = _labelled_spans(tree, label)
    print(f"{label!r} spans={spans!r}", flush=True)
    assert spans == [_keys(tagged[:3])]


def _assert_default_sentence_root(tree_a, label_a: str, tree_b, label_b: str) -> None:
    """Root is a sentence label (spelling unpinned), not either clause's chunk label."""
    root_a = node_label(tree_a)
    root_b = node_label(tree_b)
    print(
        f"sentence-root {root_a!r} vs {root_b!r}; "
        f"chunk-labels {label_a!r} {label_b!r}",
        flush=True,
    )
    assert root_a == root_b
    assert root_a != label_a
    assert root_b != label_b


# ---------------------------------------------------------------------------
# A. Optional determiner–adjective–noun grammar; caller grammar is consulted
# ---------------------------------------------------------------------------


def test_np_grammar_chunks_the_big_dog_leaves_barked_as_leaf():
    label = _runtime_label()
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_BIG_DOG)
    print(f"the-big-dog label={label!r} children={len(chunk_children(tree))}", flush=True)
    _assert_np_then_vbd_leaf(tree, THE_BIG_DOG, label)
    assert_leaves_equal(tree, THE_BIG_DOG)


def test_np_grammar_chunks_dog_only_then_barked_leaf():
    label = _runtime_label()
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), DOG_BARKED)
    print(f"dog-only label={label!r}", flush=True)
    assert_chunk_covers(tree, DOG_BARKED[:1], label)
    assert_direct_leaf(tree, DOG_BARKED[1])
    assert _labelled_spans(tree, label) == [_keys(DOG_BARKED[:1])]
    assert_leaves_equal(tree, DOG_BARKED)


def test_np_grammar_barked_alone_has_no_noun_phrase():
    label = _runtime_label()
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), BARKED_ALONE)
    children = chunk_children(tree)
    print(f"barked-alone n_children={len(children)} spans={_labelled_spans(tree, label)!r}", flush=True)
    assert len(children) == 1
    assert is_tagged_leaf(children[0])
    assert (pairing_token(children[0]), tag_value(children[0])) == ("barked", "VBD")
    assert _labelled_spans(tree, label) == []
    assert_leaves_equal(tree, BARKED_ALONE)


def test_np_grammar_determiner_noun_zero_adjectives():
    label = _runtime_label()
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_DOG_BARKED)
    print(f"zero-JJ spans={_labelled_spans(tree, label)!r}", flush=True)
    assert_chunk_covers(tree, THE_DOG_BARKED[:2], label)
    assert_direct_leaf(tree, THE_DOG_BARKED[2])
    assert _labelled_spans(tree, label) == [_keys(THE_DOG_BARKED[:2])]


def test_np_grammar_determiner_adjective_without_noun_is_not_a_chunk():
    label = _runtime_label()
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_BIG_BARKED)
    print(f"no-NN spans={_labelled_spans(tree, label)!r}", flush=True)
    assert _labelled_spans(tree, label) == []
    for pair in THE_BIG_BARKED:
        assert_direct_leaf(tree, pair)
    assert_leaves_equal(tree, THE_BIG_BARKED)


def test_np_grammar_two_adjectives_then_noun():
    label = _runtime_label()
    toks = [_runtime_token() for _ in range(5)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "JJ"),
        (toks[2], "JJ"),
        (toks[3], "NN"),
        (toks[4], "VBD"),
    ]
    print(f"two-JJ tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    assert_chunk_covers(tree, tagged[:4], label)
    assert_direct_leaf(tree, tagged[4])
    assert _labelled_spans(tree, label) == [_keys(tagged[:4])]
    assert_leaves_equal(tree, tagged)


def test_np_grammar_adjective_noun_without_determiner():
    label = _runtime_label()
    adj = _runtime_token()
    noun = _runtime_token(forbidden={adj})
    rest = _runtime_token(forbidden={adj, noun})
    tagged = [(adj, "JJ"), (noun, "NN"), (rest, "VBD")]
    print(f"JJ-NN tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    assert_chunk_covers(tree, tagged[:2], label)
    assert_direct_leaf(tree, tagged[2])
    assert _labelled_spans(tree, label) == [_keys(tagged[:2])]


def test_np_grammar_chunks_every_matching_sequence():
    label = _runtime_label()
    toks = [_runtime_token() for _ in range(5)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "NN"),
        (toks[2], "VBD"),
        (toks[3], "DT"),
        (toks[4], "NN"),
    ]
    print(f"two-matches tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    assert_chunk_covers(tree, tagged[:2], label)
    assert_chunk_covers(tree, tagged[3:], label)
    assert_direct_leaf(tree, tagged[2])
    spans = _labelled_spans(tree, label)
    assert spans == [_keys(tagged[:2]), _keys(tagged[3:])]
    assert_leaves_equal(tree, tagged)


def test_np_grammar_adjacent_matches_are_two_chunks():
    label = _runtime_label()
    toks = [_runtime_token() for _ in range(4)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "NN"),
        (toks[2], "DT"),
        (toks[3], "NN"),
    ]
    print(f"adjacent tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    assert_chunk_covers(tree, tagged[:2], label)
    assert_chunk_covers(tree, tagged[2:], label)
    spans = _labelled_spans(tree, label)
    assert spans == [_keys(tagged[:2]), _keys(tagged[2:])]
    assert [_keys(tagged)] != spans
    assert_leaves_equal(tree, tagged)


def test_np_grammar_runtime_tokens_optional_dt_jj_nn():
    label = _runtime_label()
    toks = [_runtime_token() for _ in range(4)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "JJ"),
        (toks[2], "NN"),
        (toks[3], "VBD"),
    ]
    print(f"runtime DT-JJ-NN-VBD tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    _assert_np_then_vbd_leaf(tree, tagged, label)
    assert_leaves_equal(tree, tagged)


def test_np_grammar_whitespace_in_tag_pattern_ignored():
    label = _runtime_label()
    compact = _clause(label, NP_PATTERN)
    spaced = _clause(label, NP_PATTERN_SPACED)
    # Same clause name, a different tag pattern: grammar text must be consulted
    # before compact/spaced NP writings can be treated as equivalent.
    different = _clause(label, VBD_PATTERN)
    toks = [_runtime_token() for _ in range(4)]
    runtime = [
        (toks[0], "DT"),
        (toks[1], "JJ"),
        (toks[2], "NN"),
        (toks[3], "VBD"),
    ]
    print(
        f"whitespace-ignored compact={NP_PATTERN!r} spaced={NP_PATTERN_SPACED!r} "
        f"different={VBD_PATTERN!r} runtime={runtime!r} label={label!r}",
        flush=True,
    )
    with _empty_resources():
        different_public = chunked_of(RegexpParser, different, THE_BIG_DOG)
        different_runtime = chunked_of(RegexpParser, different, runtime)
        compact_public = chunked_of(RegexpParser, compact, THE_BIG_DOG)
        spaced_public = chunked_of(RegexpParser, spaced, THE_BIG_DOG)
        compact_runtime = chunked_of(RegexpParser, compact, runtime)
        spaced_runtime = chunked_of(RegexpParser, spaced, runtime)
    print(
        f"public different={_labelled_spans(different_public, label)!r} "
        f"compact={_labelled_spans(compact_public, label)!r} "
        f"spaced={_labelled_spans(spaced_public, label)!r}",
        flush=True,
    )
    print(
        f"runtime different={_labelled_spans(different_runtime, label)!r} "
        f"compact={_labelled_spans(compact_runtime, label)!r} "
        f"spaced={_labelled_spans(spaced_runtime, label)!r}",
        flush=True,
    )
    # Live baseline: a different pattern on the same tokens does not produce
    # the optional-determiner–adjective–noun chunk (grammar consulted).
    assert_chunk_covers(different_public, [THE_BIG_DOG[3]], label)
    for pair in THE_BIG_DOG[:3]:
        assert_direct_leaf(different_public, pair)
    assert _labelled_spans(different_public, label) == [_keys([THE_BIG_DOG[3]])]
    assert_chunk_covers(different_runtime, [runtime[3]], label)
    for pair in runtime[:3]:
        assert_direct_leaf(different_runtime, pair)
    assert _labelled_spans(different_runtime, label) == [_keys([runtime[3]])]
    # Compact and spaced NP writings match each other and produce that chunk.
    _assert_np_then_vbd_leaf(compact_public, THE_BIG_DOG, label)
    _assert_np_then_vbd_leaf(spaced_public, THE_BIG_DOG, label)
    _assert_np_then_vbd_leaf(compact_runtime, runtime, label)
    _assert_np_then_vbd_leaf(spaced_runtime, runtime, label)
    assert _labelled_spans(compact_public, label) == _labelled_spans(spaced_public, label)
    assert _labelled_spans(compact_runtime, label) == _labelled_spans(
        spaced_runtime, label
    )
    assert _labelled_spans(compact_public, label) != _labelled_spans(
        different_public, label
    )
    assert _labelled_spans(compact_runtime, label) != _labelled_spans(
        different_runtime, label
    )


def test_two_grammars_differ_on_the_big_dog_list():
    label_l = _runtime_label()
    label_m = _runtime_label(forbidden={label_l})
    with _empty_resources():
        tree_l = chunked_of(RegexpParser, _np_grammar(label_l), THE_BIG_DOG)
        tree_m = chunked_of(
            RegexpParser, _clause(label_m, VBD_PATTERN), THE_BIG_DOG
        )
    print(
        f"L={label_l!r} spans={_labelled_spans(tree_l, label_l)!r} "
        f"M={label_m!r} spans={_labelled_spans(tree_m, label_m)!r}",
        flush=True,
    )
    _assert_np_then_vbd_leaf(tree_l, THE_BIG_DOG, label_l)
    assert_chunk_covers(tree_m, [THE_BIG_DOG[3]], label_m)
    for pair in THE_BIG_DOG[:3]:
        assert_direct_leaf(tree_m, pair)
    assert _labelled_spans(tree_m, label_m) == [_keys([THE_BIG_DOG[3]])]
    assert _labelled_spans(tree_l, label_l) != _labelled_spans(tree_m, label_m)


def test_runtime_tag_pattern_is_consulted():
    label = _runtime_label()
    tag_a = _runtime_tag()
    tag_b = _runtime_tag(forbidden={tag_a})
    token = _runtime_token()
    tagged = [(token, tag_a)]
    grammar_a = _clause(label, "{<" + tag_a + ">}")
    grammar_b = _clause(label, "{<" + tag_b + ">}")
    print(
        f"runtime tags Ta={tag_a!r} Tb={tag_b!r} token={token!r} label={label!r}",
        flush=True,
    )
    with _empty_resources():
        tree_a = chunked_of(RegexpParser, grammar_a, tagged)
        tree_b = chunked_of(RegexpParser, grammar_b, tagged)
    assert_chunk_covers(tree_a, tagged, label)
    assert_direct_leaf(tree_b, tagged[0])
    assert _labelled_spans(tree_a, label) == [_keys(tagged)]
    assert _labelled_spans(tree_b, label) == []


# ---------------------------------------------------------------------------
# B. Four or more consecutive N-initial tags
# ---------------------------------------------------------------------------


def _separated_n_runs(sep):
    return list(COURT_FOUR) + [sep] + list(TERM_JURY) + [sep] + list(MAYOR_FOUR)


def test_four_or_more_n_chunks_two_separated_four_token_runs_not_term_jury():
    label = _runtime_label()
    sep = (_runtime_token(), "VB")
    tagged = _separated_n_runs(sep)
    print(f"separated N runs n={len(tagged)} sep={sep!r} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _clause(label, N4_PATTERN), tagged)
    assert_chunk_covers(tree, COURT_FOUR, label)
    assert_chunk_covers(tree, MAYOR_FOUR, label)
    spans = _labelled_spans(tree, label)
    assert spans == [_keys(COURT_FOUR), _keys(MAYOR_FOUR)]
    assert _keys(TERM_JURY) not in spans
    assert_direct_leaf(tree, sep)
    for pair in TERM_JURY:
        assert_direct_leaf(tree, pair)
    assert_leaves_equal(tree, tagged)


def test_four_or_more_n_concatenated_runs_are_one_ten_token_chunk():
    label = _runtime_label()
    tagged = list(COURT_FOUR) + list(TERM_JURY) + list(MAYOR_FOUR)
    print(f"concatenated n={len(tagged)} label={label!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, _clause(label, N4_PATTERN), tagged)
    assert_chunk_covers(tree, tagged, label)
    spans = _labelled_spans(tree, label)
    assert spans == [_keys(tagged)]
    assert spans != [_keys(COURT_FOUR), _keys(MAYOR_FOUR)]
    assert_leaves_equal(tree, tagged)


def test_four_or_more_n_runtime_separated_and_concatenated():
    label = _runtime_label()
    n_tag = _runtime_n_tag()
    sep_tag = _runtime_tag()
    toks = [_runtime_token() for _ in range(11)]
    four_a = [(toks[i], n_tag) for i in range(4)]
    two = [(toks[4], n_tag), (toks[5], n_tag)]
    four_b = [(toks[i], n_tag) for i in range(6, 10)]
    sep = (toks[10], sep_tag)
    separated = four_a + [sep] + two + [sep] + four_b
    concatenated = four_a + two + four_b
    print(
        f"runtime N-tag={n_tag!r} sep_tag={sep_tag!r} label={label!r}",
        flush=True,
    )
    grammar = _clause(label, N4_PATTERN)
    with _empty_resources():
        tree_sep = chunked_of(RegexpParser, grammar, separated)
        tree_cat = chunked_of(RegexpParser, grammar, concatenated)
    assert _labelled_spans(tree_sep, label) == [_keys(four_a), _keys(four_b)]
    assert _keys(two) not in _labelled_spans(tree_sep, label)
    assert_chunk_covers(tree_cat, concatenated, label)
    assert _labelled_spans(tree_cat, label) == [_keys(concatenated)]


def test_four_or_more_n_runtime_length_threshold():
    label = _runtime_label()
    n_tag = _runtime_n_tag()
    three = [(_runtime_token(), n_tag) for _ in range(3)]
    length = 5 + (uuid.uuid4().int % 5)
    long_run = [(_runtime_token(), n_tag) for _ in range(length)]
    print(
        f"threshold N-tag={n_tag!r} three={len(three)} long={length} label={label!r}",
        flush=True,
    )
    grammar = _clause(label, N4_PATTERN)
    with _empty_resources():
        tree_three = chunked_of(RegexpParser, grammar, three)
        tree_long = chunked_of(RegexpParser, grammar, long_run)
    assert _labelled_spans(tree_three, label) == []
    for pair in three:
        assert_direct_leaf(tree_three, pair)
    assert_chunk_covers(tree_long, long_run, label)
    assert _labelled_spans(tree_long, label) == [_keys(long_run)]
    assert length not in {4, 10}


# ---------------------------------------------------------------------------
# C. Same-clause chunk-then-chink; no-chink baseline; later-clause chink
# ---------------------------------------------------------------------------


def _assert_chinked_little_cat(tree, tagged, label: str) -> None:
    assert_chunk_covers(tree, tagged[:3], label)
    assert_chunk_covers(tree, tagged[5:], label)
    assert_direct_leaf(tree, tagged[3])
    assert_direct_leaf(tree, tagged[4])
    spans = _labelled_spans(tree, label)
    print(f"chinked spans={spans!r}", flush=True)
    assert spans == [_keys(tagged[:3]), _keys(tagged[5:])]


def _assert_whole_list_one_chunk(tree, tagged, label: str) -> None:
    assert_chunk_covers(tree, tagged, label)
    spans = _labelled_spans(tree, label)
    print(f"whole-list spans={spans!r}", flush=True)
    assert spans == [_keys(tagged)]
    sat = tagged[3]
    sat_chunks = containing_chunks(tree, pairing_token(sat))
    assert any(
        node_label(node) == label
        and _keys(chunk_leaves(node)) == _keys(tagged)
        for node in sat_chunks
    )


def test_same_clause_chunk_then_chink_two_nps_sat_on_as_leaves():
    label = _runtime_label()
    grammar = _clause(label, EVERYTHING_PATTERN, CHINK_VBD_IN)
    with _empty_resources():
        tree = chunked_of(RegexpParser, grammar, LITTLE_CAT)
    _assert_chinked_little_cat(tree, LITTLE_CAT, label)
    assert_leaves_equal(tree, LITTLE_CAT)


def test_chunk_everything_without_chink_is_one_noun_phrase():
    label = _runtime_label()
    grammar = _clause(label, EVERYTHING_PATTERN)
    with _empty_resources():
        tree = chunked_of(RegexpParser, grammar, LITTLE_CAT)
    _assert_whole_list_one_chunk(tree, LITTLE_CAT, label)
    assert_leaves_equal(tree, LITTLE_CAT)


def test_later_clause_chink_leaves_whole_list_one_noun_phrase():
    label = _runtime_label()
    other = _runtime_label(forbidden={label})
    grammar = _clause(label, EVERYTHING_PATTERN) + "\n" + _clause(other, CHINK_VBD_IN)
    with _empty_resources():
        tree = chunked_of(RegexpParser, grammar, LITTLE_CAT)
    print(f"later-clause chink L={label!r} X={other!r}", flush=True)
    _assert_whole_list_one_chunk(tree, LITTLE_CAT, label)
    assert _labelled_spans(tree, other) == []
    assert_leaves_equal(tree, LITTLE_CAT)


def test_same_clause_chink_runtime_tokens():
    label = _runtime_label()
    other = _runtime_label(forbidden={label})
    toks = [_runtime_token() for _ in range(7)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "JJ"),
        (toks[2], "NN"),
        (toks[3], "VBD"),
        (toks[4], "IN"),
        (toks[5], "DT"),
        (toks[6], "NN"),
    ]
    same = _clause(label, EVERYTHING_PATTERN, CHINK_VBD_IN)
    none = _clause(label, EVERYTHING_PATTERN)
    later = _clause(label, EVERYTHING_PATTERN) + "\n" + _clause(other, CHINK_VBD_IN)
    print(f"runtime chink tagged={tagged!r} label={label!r}", flush=True)
    with _empty_resources():
        tree_same = chunked_of(RegexpParser, same, tagged)
        tree_none = chunked_of(RegexpParser, none, tagged)
        tree_later = chunked_of(RegexpParser, later, tagged)
    _assert_chinked_little_cat(tree_same, tagged, label)
    _assert_whole_list_one_chunk(tree_none, tagged, label)
    _assert_whole_list_one_chunk(tree_later, tagged, label)


# ---------------------------------------------------------------------------
# D. Later clause chunks remaining VBD
# ---------------------------------------------------------------------------


def test_later_clause_chunks_remaining_vbd_after_noun_phrase():
    label1 = _runtime_label()
    label2 = _runtime_label(forbidden={label1})
    grammar = _clause(label1, NP_PATTERN) + "\n" + _clause(label2, VBD_PATTERN)
    with _empty_resources():
        tree = chunked_of(RegexpParser, grammar, THE_BIG_DOG)
    print(f"cascade L1={label1!r} L2={label2!r}", flush=True)
    assert_chunk_covers(tree, THE_BIG_DOG[:3], label1)
    assert_chunk_covers(tree, [THE_BIG_DOG[3]], label2)
    barked_chunks = containing_chunks(tree, "barked")
    assert all(node_label(node) != label1 for node in barked_chunks)
    assert_leaves_equal(tree, THE_BIG_DOG)


def test_later_clause_chunks_remaining_vbd_runtime_tokens():
    label1 = _runtime_label()
    label2 = _runtime_label(forbidden={label1})
    toks = [_runtime_token() for _ in range(4)]
    tagged = [
        (toks[0], "DT"),
        (toks[1], "JJ"),
        (toks[2], "NN"),
        (toks[3], "VBD"),
    ]
    grammar = _clause(label1, NP_PATTERN) + "\n" + _clause(label2, VBD_PATTERN)
    print(f"runtime cascade tagged={tagged!r} L1={label1!r} L2={label2!r}", flush=True)
    with _empty_resources():
        tree = chunked_of(RegexpParser, grammar, tagged)
    assert_chunk_covers(tree, tagged[:3], label1)
    assert_chunk_covers(tree, [tagged[3]], label2)
    barked_chunks = containing_chunks(tree, toks[3])
    assert all(node_label(node) != label1 for node in barked_chunks)
    assert_leaves_equal(tree, tagged)


# ---------------------------------------------------------------------------
# E. Leaves equal the input
# ---------------------------------------------------------------------------


def test_chunk_leaves_equal_input_on_named_sentences():
    label_a = _runtime_label()
    label_c = _runtime_label(forbidden={label_a})
    label_b = _runtime_label(forbidden={label_a, label_c})
    sep = (_runtime_token(), "VB")
    separated = _separated_n_runs(sep)
    with _empty_resources():
        tree_a = chunked_of(RegexpParser, _np_grammar(label_a), THE_BIG_DOG)
        tree_c = chunked_of(
            RegexpParser,
            _clause(label_c, EVERYTHING_PATTERN, CHINK_VBD_IN),
            LITTLE_CAT,
        )
        tree_b = chunked_of(RegexpParser, _clause(label_b, N4_PATTERN), separated)
    assert_leaves_equal(tree_a, THE_BIG_DOG)
    assert_leaves_equal(tree_c, LITTLE_CAT)
    assert_leaves_equal(tree_b, separated)


def test_chunk_leaves_equal_input_on_runtime_tagged_list():
    label = _runtime_label()
    # Public named-sentence lengths are 4 (the-big-dog) and 7 (little-cat).
    # Draw from {5, 6, 8, 9} so this cousin is never those table sizes.
    length = (5, 6, 8, 9)[uuid.uuid4().int % 4]
    tagged = [(_runtime_token(), "NN" if i % 2 else "DT") for i in range(length)]
    print(f"runtime leaves n={length} tagged={tagged!r}", flush=True)
    assert length not in {4, 7}
    with _empty_resources():
        tree = chunked_of(RegexpParser, _np_grammar(label), tagged)
    assert_leaves_equal(tree, tagged)


# ---------------------------------------------------------------------------
# F. Sentence-root default; empty list; non-grammar value refused
# ---------------------------------------------------------------------------


def test_chunk_structure_root_defaults_to_sentence_label():
    label_a = _runtime_label()
    label_b = _runtime_label(forbidden={label_a})
    with _empty_resources():
        tree_a = chunked_of(RegexpParser, _np_grammar(label_a), THE_BIG_DOG)
        tree_b = chunked_of(RegexpParser, _np_grammar(label_b), THE_BIG_DOG)
    _assert_default_sentence_root(tree_a, label_a, tree_b, label_b)
    _assert_np_then_vbd_leaf(tree_a, THE_BIG_DOG, label_a)
    _assert_np_then_vbd_leaf(tree_b, THE_BIG_DOG, label_b)
    assert_leaves_equal(tree_a, THE_BIG_DOG)
    assert_leaves_equal(tree_b, THE_BIG_DOG)


def test_empty_tagged_list_sentence_root_no_children():
    label_a = _runtime_label()
    label_b = _runtime_label(forbidden={label_a})
    with _empty_resources():
        tree_a = chunked_of(RegexpParser, _np_grammar(label_a), [])
        tree_b = chunked_of(RegexpParser, _np_grammar(label_b), [])
    children_a = chunk_children(tree_a)
    children_b = chunk_children(tree_b)
    leaves_a = chunk_leaves(tree_a)
    leaves_b = chunk_leaves(tree_b)
    root_a = node_label(tree_a)
    print(
        f"empty-list root={root_a!r} n_children={len(children_a)} leaves={leaves_a!r}",
        flush=True,
    )
    assert isinstance(root_a, str)
    assert isinstance(node_label(tree_b), str)
    _assert_default_sentence_root(tree_a, label_a, tree_b, label_b)
    assert children_a == []
    assert children_b == []
    assert leaves_a == []
    assert leaves_b == []
    assert _labelled_spans(tree_a, label_a) == []
    assert _labelled_spans(tree_b, label_b) == []


def test_non_text_non_stage_grammar_is_refused():
    label = _runtime_label()
    key = _runtime_token()
    with _empty_resources():
        require_grammar_refused(call(RegexpParser, 17))
        require_grammar_refused(call(RegexpParser, {key: 1}))
        require_grammar_refused(call(RegexpParser, [key, _runtime_token()]))
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_BIG_DOG)
    _assert_np_then_vbd_leaf(tree, THE_BIG_DOG, label)


# ---------------------------------------------------------------------------
# G. Named-entity path is resource-gated; grammar path is not
# ---------------------------------------------------------------------------


def test_named_entity_fails_without_resource_chunk_grammar_still_works():
    label = _runtime_label()
    with _empty_resources():
        refused = require_chunking_unsuccessful(call(ne_chunk, THE_BIG_DOG))
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_BIG_DOG)
    print(f"empty-dir NE unsuccessful={refused.exception!r}", flush=True)
    _assert_np_then_vbd_leaf(tree, THE_BIG_DOG, label)


def test_named_entity_fails_without_ne_resource_when_perceptron_present():
    label = _runtime_label()
    with _perceptron_without_ne():
        tagged = tagged_of(pos_tag, HOMEPAGE)
        print(f"perceptron-only homepage tagged n={len(tagged)}", flush=True)
        assert len(tagged) == 13
        refused = require_chunking_unsuccessful(call(ne_chunk, tagged))
        tree = chunked_of(RegexpParser, _np_grammar(label), THE_BIG_DOG)
    print(f"perceptron-only NE unsuccessful={refused.exception!r}", flush=True)
    _assert_np_then_vbd_leaf(tree, THE_BIG_DOG, label)
