# feature: F03
"""Part-of-speech tagging (FP-03).

Named tags are asserted at the PRD's precision. Category structure uses
same-tag / distinct-tag contrasts rather than checkout-only codes.
Missing-resource and raw-string refusals are distinguished from a
successful aligned tagged list. Exception types and message wording
are not pinned.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from lingora.tag import DefaultTagger, RegexpTagger, UnigramTagger, pos_tag

from _harness import CallResult, HarnessError, call, workspace
from _helpers import (
    assert_distinct_tags,
    assert_same_tag,
    assert_tag_absent,
    assert_tag_equals,
    bound_resource_path,
    english_universal_mapping_absent,
    install_perceptron,
    install_universal_tagset,
    require_no_tagged_sequence,
    require_tagging_unsuccessful,
    tag_value,
    tagged_of,
)

LANG_ENG = "eng"
LANG_RUS = "rus"
LANG_KOREAN = "Korean"
TAGSET_UNIVERSAL = "universal"

THIS_IS_A_TEST = ["This", "is", "a", "test"]

TRAIN_THE_DOG_CAT = [
    [("the", "DT"), ("dog", "NN")],
    [("the", "DT"), ("cat", "NN")],
]

SAW_3_DOGS = ["saw", "3", "dogs"]
NUMBER_RULE = [(r"^[0-9]+$", "CD")]

JOHN = ["John", "'s", "big", "idea", "is", "n't", "all", "that", "bad", "."]
JOHN_RAW = "John's big idea isn't all that bad."

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

ILYA = ["Илья", "оторопел", "и", "дважды", "перечитал", "бумажку", "."]

JOHN_PTB_GROUPS = {
    "proper": ["John"],
    "poss": ["'s"],
    "adj": ["big", "bad"],
    "common": ["idea"],
    "verb3sg": ["is"],
    "adv": ["n't"],
    "predet": ["all"],
    "det": ["that"],
    "punct": ["."],
}

ILYA_RNC_GROUPS = {
    "noun": ["Илья", "бумажку"],
    "verb": ["оторопел", "перечитал"],
    "conj": ["и"],
    "adv": ["дважды"],
    "nonlex": ["."],
}

_CHILD_TAG_MARK = "F03TAG"


def _alpha_token(*, forbidden: set[str] | None = None, n: int = 8) -> str:
    blocked = set(forbidden or ())
    blocked.update({"the", "dog", "cat", "xyz", "saw", "dogs", "This", "test"})
    while True:
        raw = uuid.uuid4().hex
        tok = "".join("abcdefghijklmnop"[int(c, 16)] for c in raw[:n])
        if tok.isalpha() and tok not in blocked:
            return tok


def _runtime_tag(*, forbidden: set[str] | None = None) -> str:
    blocked = set(forbidden or ())
    blocked.update({"NN", "DT", "CD", "S", "V", "UNK", "NOUN", "VERB"})
    while True:
        tag = "Z" + uuid.uuid4().hex[:6].upper()
        if tag.isalpha() and tag not in blocked:
            return tag


def _runtime_digits() -> str:
    return str(10 + (uuid.uuid4().int % 90))


def _unsupported_language_name() -> str:
    blocked = {
        LANG_ENG,
        LANG_RUS,
        LANG_KOREAN,
        "eng",
        "rus",
        "kor",
        "english",
        "russian",
        "korean",
        "English",
        "Russian",
        "en",
        "ru",
    }
    while True:
        name = _alpha_token(forbidden=blocked, n=10)
        if name not in blocked:
            return name


@contextmanager
def _empty_resources():
    """No packaged tagger models on the search list."""
    with workspace() as ws:
        with bound_resource_path(ws, present=False):
            yield ws


@contextmanager
def _tagger_resources(*languages: str, universal: bool = False):
    """Install only the named perceptron trees, optionally the universal tables."""
    with workspace() as ws:
        for language in languages:
            install_perceptron(ws, language)
        if universal:
            install_universal_tagset(ws)
        with bound_resource_path(ws, present=True):
            yield ws


def _constructed_tagger(cls, *args, **kwargs):
    result = call(cls, *args, **kwargs)
    if result.exception is not None:
        raise AssertionError(
            "tagger constructor failed: "
            f"{type(result.exception).__name__}: {result.exception}"
        )
    inst = result.value
    if not callable(getattr(inst, "tag", None)):
        raise AssertionError(
            f"constructed value has no callable tag: {type(inst).__name__} {inst!r}"
        )
    return inst


def _pair_at(pairs, tokens, word):
    return pairs[list(tokens).index(word)]


def _assert_category_groups(pairs, tokens, groups: dict[str, list[str]]) -> None:
    """Same named category → same tag; different named categories → distinct tags."""
    for pairing in pairs:
        tag_value(pairing)
    reps = {}
    for name, words in groups.items():
        first = _pair_at(pairs, tokens, words[0])
        for word in words[1:]:
            assert_same_tag(first, _pair_at(pairs, tokens, word))
        reps[name] = first
    names = list(reps)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            assert_distinct_tags(reps[left], reps[right])


def _child_pos_tag(ws, payload, *, lang: str | None = None, tagset: str | None = None):
    """Recommended tagger in a child so in-process mapping tables cannot leak."""
    data_dir = str(Path(ws.data).resolve())
    kwargs = {}
    if lang is not None:
        kwargs["lang"] = lang
    if tagset is not None:
        kwargs["tagset"] = tagset
    code = (
        "import json\n"
        "from lingora import data\n"
        f"data.path[:] = [{data_dir!r}]\n"
        "from lingora.tag import pos_tag\n"
        f"payload = {payload!r}\n"
        f"kwargs = {kwargs!r}\n"
        "try:\n"
        "    tagged = pos_tag(payload, **kwargs)\n"
        "except Exception as exc:\n"
        f"    print({_CHILD_TAG_MARK!r} + json.dumps("
        "{'k': 'exc', 't': type(exc).__name__, 'm': str(exc)}), flush=True)\n"
        "else:\n"
        "    def enc(x):\n"
        "        if isinstance(x, tuple):\n"
        "            return [enc(i) for i in x]\n"
        "        if isinstance(x, list):\n"
        "            return [enc(i) for i in x]\n"
        "        if x is None or isinstance(x, (str, int, float, bool)):\n"
        "            return x\n"
        "        return str(x)\n"
        f"    print({_CHILD_TAG_MARK!r} + json.dumps("
        "{'k': 'ok', 'v': enc(tagged)}), flush=True)\n"
    )
    ran = ws.run_python(code=code)
    if ran.returncode != 0:
        raise HarnessError(
            "child recommended tagger exited non-zero: "
            f"rc={ran.returncode} stderr={ran.stderr_text!r} stdout={ran.stdout_text!r}"
        )
    line = None
    for row in ran.stdout_text.splitlines():
        if row.startswith(_CHILD_TAG_MARK):
            line = row[len(_CHILD_TAG_MARK) :]
    if line is None:
        raise HarnessError(
            "child recommended tagger produced no observation: "
            f"stdout={ran.stdout_text!r} stderr={ran.stderr_text!r}"
        )
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"child recommended tagger observation is not JSON: {line!r}"
        ) from exc
    if msg.get("k") == "exc":
        return CallResult(
            value=None,
            exception=Exception(msg.get("m", "")),
            exc_info=None,
            stdout=ran.stdout,
            stderr=ran.stderr,
            cwd=str(ws.path),
        )
    if msg.get("k") == "ok":
        return CallResult(
            value=msg.get("v"),
            exception=None,
            exc_info=None,
            stdout=ran.stdout,
            stderr=ran.stderr,
            cwd=str(ws.path),
        )
    raise HarnessError(f"child recommended tagger observation is unclassifiable: {msg!r}")


# ---------------------------------------------------------------------------
# A. Default tagger
# ---------------------------------------------------------------------------


def test_default_tagger_nn_on_this_is_a_test():
    with _empty_resources():
        tagger = _constructed_tagger(DefaultTagger, "NN")
        pairs = tagged_of(tagger.tag, THIS_IS_A_TEST)
    print(f"default NN on This is a test={pairs!r}", flush=True)
    assert len(pairs) == 4
    for pairing in pairs:
        assert_tag_equals(pairing, "NN")


def test_default_tagger_runtime_tag_applies_to_every_token():
    tag = _runtime_tag(forbidden={"NN"})
    tokens = [_alpha_token() for _ in range(3)]
    print(f"runtime default tag={tag!r} tokens={tokens!r}", flush=True)
    with _empty_resources():
        tagger = _constructed_tagger(DefaultTagger, tag)
        pairs = tagged_of(tagger.tag, tokens)
    assert len(pairs) == 3
    for pairing in pairs:
        assert_tag_equals(pairing, tag)


# ---------------------------------------------------------------------------
# B. Unigram: seen words from training; unseen untagged
# ---------------------------------------------------------------------------


def test_unigram_trained_the_dog_and_cat_tags_seen_words():
    with _empty_resources():
        tagger = _constructed_tagger(UnigramTagger, train=TRAIN_THE_DOG_CAT)
        dog_pairs = tagged_of(tagger.tag, ["the", "dog"])
        cat_pairs = tagged_of(tagger.tag, ["the", "cat"])
    print(f"unigram the/dog={dog_pairs!r} the/cat={cat_pairs!r}", flush=True)
    assert_tag_equals(dog_pairs[0], "DT")
    assert_tag_equals(dog_pairs[1], "NN")
    assert_tag_equals(cat_pairs[0], "DT")
    assert_tag_equals(cat_pairs[1], "NN")


def test_unigram_leaves_xyz_untagged_unlike_default_nn():
    with _empty_resources():
        unigram = _constructed_tagger(UnigramTagger, train=TRAIN_THE_DOG_CAT)
        default = _constructed_tagger(DefaultTagger, "NN")
        uni_pairs = tagged_of(unigram.tag, ["the", "xyz"])
        def_pairs = tagged_of(default.tag, ["xyz"])
    print(f"unigram the/xyz={uni_pairs!r} default xyz={def_pairs!r}", flush=True)
    assert_tag_equals(uni_pairs[0], "DT")
    assert_tag_absent(uni_pairs[1])
    assert_tag_equals(def_pairs[0], "NN")


def test_unigram_runtime_seen_and_unseen_tokens():
    tok_a = _alpha_token()
    tok_b = _alpha_token(forbidden={tok_a})
    tok_c = _alpha_token(forbidden={tok_a, tok_b})
    tag1 = _runtime_tag(forbidden={"DT", "NN"})
    tag2 = _runtime_tag(forbidden={"DT", "NN", tag1})
    print(
        f"runtime unigram {tok_a}/{tag1} {tok_b}/{tag2} unseen={tok_c!r}",
        flush=True,
    )
    train = [[(tok_a, tag1)], [(tok_b, tag2)]]
    with _empty_resources():
        tagger = _constructed_tagger(UnigramTagger, train=train)
        a_pairs = tagged_of(tagger.tag, [tok_a])
        b_pairs = tagged_of(tagger.tag, [tok_b])
        c_pairs = tagged_of(tagger.tag, [tok_c])
    assert_tag_equals(a_pairs[0], tag1)
    assert_tag_equals(b_pairs[0], tag2)
    assert_tag_absent(c_pairs[0])


# ---------------------------------------------------------------------------
# C. Backoff fills only untagged positions
# ---------------------------------------------------------------------------


def test_unigram_backoff_nn_tags_xyz_keeps_the_as_dt():
    with _empty_resources():
        backoff = _constructed_tagger(DefaultTagger, "NN")
        tagger = _constructed_tagger(
            UnigramTagger, train=TRAIN_THE_DOG_CAT, backoff=backoff
        )
        pairs = tagged_of(tagger.tag, ["the", "xyz"])
    print(f"unigram+backoff the/xyz={pairs!r}", flush=True)
    assert_tag_equals(pairs[0], "DT")
    assert_tag_equals(pairs[1], "NN")


def test_unigram_backoff_runtime_fills_only_unseen():
    tok_a = _alpha_token()
    tok_c = _alpha_token(forbidden={tok_a})
    tag1 = _runtime_tag(forbidden={"NN"})
    tag2 = _runtime_tag(forbidden={"NN", tag1})
    print(
        f"runtime backoff primary={tok_a}/{tag1} backoff={tag2} unseen={tok_c!r}",
        flush=True,
    )
    with _empty_resources():
        backoff = _constructed_tagger(DefaultTagger, tag2)
        tagger = _constructed_tagger(
            UnigramTagger, train=[[(tok_a, tag1)]], backoff=backoff
        )
        a_pairs = tagged_of(tagger.tag, [tok_a])
        c_pairs = tagged_of(tagger.tag, [tok_c])
    assert_tag_equals(a_pairs[0], tag1)
    assert_tag_equals(c_pairs[0], tag2)


# ---------------------------------------------------------------------------
# D. Regular-expression tagger; empty lists
# ---------------------------------------------------------------------------


def test_regexp_number_rule_tags_3_as_cd_leaves_saw_dogs_untagged():
    with _empty_resources():
        tagger = _constructed_tagger(RegexpTagger, NUMBER_RULE)
        pairs = tagged_of(tagger.tag, SAW_3_DOGS)
    print(f"regexp saw/3/dogs={pairs!r}", flush=True)
    assert_tag_absent(pairs[0])
    assert_tag_equals(pairs[1], "CD")
    assert_tag_absent(pairs[2])


def test_regexp_runtime_digits_cd_non_number_untagged():
    digits = _runtime_digits()
    word = _alpha_token()
    print(f"runtime regexp digits={digits!r} word={word!r}", flush=True)
    with _empty_resources():
        tagger = _constructed_tagger(RegexpTagger, NUMBER_RULE)
        pairs = tagged_of(tagger.tag, [digits, word])
    assert_tag_equals(pairs[0], "CD")
    assert_tag_absent(pairs[1])


def test_regexp_two_configs_differ_on_shared_token():
    token_t = _alpha_token()
    tag_r = _runtime_tag(forbidden={"CD", "NN"})
    other_rule = [(rf"^{re.escape(token_t)}$", tag_r)]
    print(f"shared token={token_t!r} second-config tag={tag_r!r}", flush=True)
    with _empty_resources():
        numbers = _constructed_tagger(RegexpTagger, NUMBER_RULE)
        other = _constructed_tagger(RegexpTagger, other_rule)
        number_pairs = tagged_of(numbers.tag, [token_t])
        other_pairs = tagged_of(other.tag, [token_t])
    assert_tag_absent(number_pairs[0])
    assert_tag_equals(other_pairs[0], tag_r)


def test_regexp_backoff_fills_non_number_keeps_cd():
    with _empty_resources():
        plain = _constructed_tagger(RegexpTagger, NUMBER_RULE)
        baseline = tagged_of(plain.tag, SAW_3_DOGS)
        backoff = _constructed_tagger(DefaultTagger, "NN")
        filled = _constructed_tagger(RegexpTagger, NUMBER_RULE, backoff=backoff)
        pairs = tagged_of(filled.tag, SAW_3_DOGS)
    print(f"regexp no-backoff={baseline!r} with-backoff={pairs!r}", flush=True)
    assert_tag_absent(baseline[0])
    assert_tag_equals(baseline[1], "CD")
    assert_tag_equals(pairs[0], "NN")
    assert_tag_equals(pairs[1], "CD")


def test_empty_token_list_tags_as_empty_on_graded_trainables():
    with _empty_resources():
        default = tagged_of(_constructed_tagger(DefaultTagger, "NN").tag, [])
        unigram = tagged_of(
            _constructed_tagger(UnigramTagger, train=TRAIN_THE_DOG_CAT).tag, []
        )
        regexp = tagged_of(_constructed_tagger(RegexpTagger, NUMBER_RULE).tag, [])
    print(
        f"empty default={default!r} unigram={unigram!r} regexp={regexp!r}",
        flush=True,
    )
    assert default == []
    assert unigram == []
    assert regexp == []


def test_empty_token_list_tags_as_empty_on_recommended_english():
    with _tagger_resources(LANG_ENG, universal=False):
        pairs = tagged_of(pos_tag, [])
    print(f"recommended english empty={pairs!r}", flush=True)
    assert pairs == []


# ---------------------------------------------------------------------------
# E. Recommended English Penn Treebank categories
# ---------------------------------------------------------------------------


def test_recommended_english_john_list_ptb_category_structure():
    with _tagger_resources(LANG_ENG, universal=False):
        pairs = tagged_of(pos_tag, JOHN)
    print(f"recommended english John PTB={pairs!r}", flush=True)
    assert len(pairs) == 10
    _assert_category_groups(pairs, JOHN, JOHN_PTB_GROUPS)


def test_recommended_english_homepage_proper_vs_common_noun():
    with _tagger_resources(LANG_ENG, universal=False):
        john_pairs = tagged_of(pos_tag, JOHN)
        home_pairs = tagged_of(pos_tag, HOMEPAGE)
    print(f"homepage PTB={home_pairs!r}", flush=True)
    thursday = _pair_at(home_pairs, HOMEPAGE, "Thursday")
    arthur = _pair_at(home_pairs, HOMEPAGE, "Arthur")
    morning = _pair_at(home_pairs, HOMEPAGE, "morning")
    assert_same_tag(thursday, arthur)
    assert_distinct_tags(thursday, morning)
    assert_same_tag(thursday, _pair_at(john_pairs, JOHN, "John"))
    assert_same_tag(morning, _pair_at(john_pairs, JOHN, "idea"))


# ---------------------------------------------------------------------------
# F. Russian RNC and universal
# English mapping with the tables present is outside the specification.
# ---------------------------------------------------------------------------


def test_recommended_russian_rnc_named_s_v_and_category_contrasts():
    with _tagger_resources(LANG_RUS, universal=False):
        pairs = tagged_of(pos_tag, ILYA, lang=LANG_RUS)
    print(f"russian RNC Илья={pairs!r}", flush=True)
    assert_tag_equals(_pair_at(pairs, ILYA, "Илья"), "S")
    assert_tag_equals(_pair_at(pairs, ILYA, "оторопел"), "V")
    _assert_category_groups(pairs, ILYA, ILYA_RNC_GROUPS)


def test_recommended_russian_universal_maps_noun_and_verb():
    with _tagger_resources(LANG_RUS, universal=False):
        rnc = tagged_of(pos_tag, ILYA, lang=LANG_RUS)
        univ = tagged_of(pos_tag, ILYA, lang=LANG_RUS, tagset=TAGSET_UNIVERSAL)
    print(f"russian universal Илья={univ!r}", flush=True)
    assert_same_tag(_pair_at(univ, ILYA, "Илья"), _pair_at(univ, ILYA, "бумажку"))
    assert_same_tag(
        _pair_at(univ, ILYA, "оторопел"), _pair_at(univ, ILYA, "перечитал")
    )
    noun = tag_value(_pair_at(univ, ILYA, "Илья"))
    verb = tag_value(_pair_at(univ, ILYA, "оторопел"))
    assert noun != "S"
    assert verb != "V"
    assert noun != verb
    assert_tag_equals(_pair_at(rnc, ILYA, "Илья"), "S")
    assert_tag_equals(_pair_at(rnc, ILYA, "оторопел"), "V")


# ---------------------------------------------------------------------------
# G. Raw string, unsupported language, missing perceptron
# ---------------------------------------------------------------------------


def test_recommended_refuses_raw_john_string_token_list_succeeds():
    with _tagger_resources(LANG_ENG, universal=False):
        refused = require_no_tagged_sequence(call(pos_tag, JOHN_RAW))
        listed = tagged_of(pos_tag, JOHN)
    print(f"raw John refusal={refused.exception!r} list={listed!r}", flush=True)
    assert len(listed) == 10


def test_recommended_refuses_runtime_raw_string_token_list_succeeds():
    raw = "Qx" + uuid.uuid4().hex[:8] + " zy."
    tokens = [raw[:4], raw[4:8], "."]
    print(f"runtime raw={raw!r} tokens={tokens!r}", flush=True)
    with _tagger_resources(LANG_ENG, universal=False):
        refused = require_no_tagged_sequence(call(pos_tag, raw))
        listed = tagged_of(pos_tag, tokens)
    print(
        f"runtime raw refusal={refused.exception!r} list={listed!r}",
        flush=True,
    )
    assert len(listed) == 3


def test_recommended_korean_does_not_succeed_english_does():
    with _tagger_resources(LANG_ENG, universal=False):
        english = tagged_of(pos_tag, JOHN, lang=LANG_ENG)
        korean = require_tagging_unsuccessful(
            call(pos_tag, JOHN, lang=LANG_KOREAN), JOHN
        )
    print(
        f"english listed={english!r} korean unsuccessful={korean.exception!r}",
        flush=True,
    )
    assert len(english) == 10


def test_recommended_runtime_unsupported_language_does_not_succeed():
    name = _unsupported_language_name()
    print(f"runtime unsupported language={name!r}", flush=True)
    with _tagger_resources(LANG_ENG, universal=False):
        english = tagged_of(pos_tag, JOHN, lang=LANG_ENG)
        refused = require_tagging_unsuccessful(
            call(pos_tag, JOHN, lang=name), JOHN
        )
    print(
        f"unsupported {name!r} unsuccessful={refused.exception!r}",
        flush=True,
    )
    assert len(english) == 10


def test_recommended_fails_without_perceptron_trainable_taggers_do_not():
    with _empty_resources():
        refused = require_tagging_unsuccessful(call(pos_tag, JOHN), JOHN)
        default = tagged_of(_constructed_tagger(DefaultTagger, "NN").tag, THIS_IS_A_TEST)
        unigram = tagged_of(
            _constructed_tagger(UnigramTagger, train=TRAIN_THE_DOG_CAT).tag,
            ["the", "dog"],
        )
    print(
        f"missing perceptron unsuccessful={refused.exception!r} "
        f"default={default!r} unigram={unigram!r}",
        flush=True,
    )
    for pairing in default:
        assert_tag_equals(pairing, "NN")
    assert_tag_equals(unigram[0], "DT")
    assert_tag_equals(unigram[1], "NN")


def test_recommended_russian_fails_when_only_english_perceptron_installed():
    with _tagger_resources(LANG_ENG, universal=False):
        english = tagged_of(pos_tag, JOHN, lang=LANG_ENG)
        russian = require_tagging_unsuccessful(
            call(pos_tag, ILYA, lang=LANG_RUS), ILYA
        )
    print(
        f"english-only english={english!r} russian unsuccessful={russian.exception!r}",
        flush=True,
    )
    assert len(english) == 10


def test_recommended_english_fails_when_only_russian_perceptron_installed():
    with _tagger_resources(LANG_RUS, universal=False):
        russian = tagged_of(pos_tag, ILYA, lang=LANG_RUS)
        english = require_tagging_unsuccessful(
            call(pos_tag, JOHN, lang=LANG_ENG), JOHN
        )
    print(
        f"russian-only russian={russian!r} english unsuccessful={english.exception!r}",
        flush=True,
    )
    assert_tag_equals(_pair_at(russian, ILYA, "Илья"), "S")
    assert_tag_equals(_pair_at(russian, ILYA, "оторопел"), "V")


# ---------------------------------------------------------------------------
# H. English universal tables required; Russian mapping does not need them
# ---------------------------------------------------------------------------


def test_english_universal_mapping_absent_without_tables_ptb_still_works():
    with _tagger_resources(LANG_ENG, universal=False) as ws:
        ptb = tagged_of(pos_tag, JOHN)
        mapped = english_universal_mapping_absent(
            _child_pos_tag(ws, JOHN, tagset=TAGSET_UNIVERSAL), JOHN
        )
    print(f"PTB without tables={ptb!r} universal-absent={mapped!r}", flush=True)
    _assert_category_groups(ptb, JOHN, JOHN_PTB_GROUPS)


def test_russian_universal_succeeds_without_universal_tables_english_does_not():
    with _tagger_resources(LANG_ENG, LANG_RUS, universal=False) as ws:
        russian = tagged_of(
            pos_tag, ILYA, lang=LANG_RUS, tagset=TAGSET_UNIVERSAL
        )
        english = english_universal_mapping_absent(
            _child_pos_tag(ws, JOHN, tagset=TAGSET_UNIVERSAL), JOHN
        )
    print(
        f"russian universal without tables={russian!r} "
        f"english mapping-absent={english!r}",
        flush=True,
    )
    assert_same_tag(
        _pair_at(russian, ILYA, "Илья"), _pair_at(russian, ILYA, "бумажку")
    )
    assert_same_tag(
        _pair_at(russian, ILYA, "оторопел"), _pair_at(russian, ILYA, "перечитал")
    )
    noun = tag_value(_pair_at(russian, ILYA, "Илья"))
    verb = tag_value(_pair_at(russian, ILYA, "оторопел"))
    assert noun != "S"
    assert verb != "V"
    assert noun != verb
