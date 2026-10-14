# feature: F02
"""Stemming (FP-02).

Named stems are asserted at the PRD's precision. Construction failure,
unsupported-language identification, skip-on leave-unchanged of the
named tokens, and a caller-supplied suffix pattern use contrasts or
runtime inputs. Exception types, message wording, and exit-code
numbers are not pinned.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

from lingora.stem import (
    ARLSTem,
    ARLSTem2,
    LancasterStemmer,
    PorterStemmer,
    RegexpStemmer,
    SnowballStemmer,
    WordNetLemmatizer,
)

from _harness import call, run_python, workspace
from _helpers import (
    bound_resource_path,
    require_constructed,
    require_no_lemma,
    require_not_constructed,
    stem_of,
    unsuccessful_observation,
    write_stopwords_list,
)

# Snowball names listed in FP-02. Used only to generate a name that is
# not in that closed set; the product's .languages tuple is not pinned.
SNOWBALL_LISTED = frozenset(
    {
        "arabic",
        "danish",
        "dutch",
        "english",
        "finnish",
        "french",
        "german",
        "hungarian",
        "italian",
        "norwegian",
        "porter",
        "portuguese",
        "romanian",
        "russian",
        "spanish",
        "swedish",
    }
)

PORTER_PAIRS = (
    ("caresses", "caress"),
    ("flies", "fli"),
    ("dies", "die"),
    ("mules", "mule"),
    ("denied", "deni"),
    ("died", "die"),
    ("agreed", "agre"),
    ("owned", "own"),
    ("humbled", "humbl"),
    ("sized", "size"),
    ("meeting", "meet"),
    ("stating", "state"),
    ("siezing", "siez"),
    ("itemization", "item"),
    ("sensational", "sensat"),
    ("traditional", "tradit"),
    ("reference", "refer"),
    ("colonizer", "colon"),
    ("plotted", "plot"),
)

LANCASTER_PAIRS = (
    ("maximum", "maxim"),
    ("presumably", "presum"),
    ("multiply", "multiply"),
    ("owed", "ow"),
    ("saying", "say"),
    ("crying", "cry"),
    ("cement", "cem"),
)

ARABIC_PAIRS = (
    ("العربية", "عرب"),
    ("الطالبات", "طالب"),
    ("فقالوا", "قال"),
)

# Named stems for the ten further Snowball languages (stem != original).
SNOWBALL_NAMED_PAIRS = {
    "danish": (
        ("indflydelse", "indflyd"),
        ("løbende", "løb"),
        ("børnene", "børn"),
    ),
    "dutch": (
        ("opgravingen", "opgrav"),
        ("fietsen", "fiets"),
        ("wandeling", "wandel"),
    ),
    "finnish": (
        ("lapset", "laps"),
        ("taloissa", "talo"),
        ("kirjoittaa", "kirjoit"),
    ),
    "french": (
        ("continuait", "continu"),
        ("bicyclettes", "bicyclet"),
        ("chanterait", "chant"),
    ),
    "hungarian": (
        ("gyerekek", "gyerek"),
        ("házakban", "ház"),
        ("írni", "írn"),
    ),
    "italian": (
        ("continuando", "continu"),
        ("correndo", "corr"),
        ("bambini", "bambin"),
    ),
    "norwegian": (
        ("havnedistriktene", "havnedistrikt"),
        ("løpende", "løp"),
        ("husene", "hus"),
    ),
    "portuguese": (
        ("continuamente", "continu"),
        ("bicicletas", "biciclet"),
        ("crianças", "crianc"),
    ),
    "romanian": (
        ("continuare", "continu"),
        ("alergând", "alerg"),
        ("casele", "cas"),
    ),
    "swedish": (
        ("undergått", "undergåt"),
        ("löpande", "löp"),
        ("barnen", "barn"),
    ),
}

TRAILING_ING = "ing$"


def _alpha_token(*, forbidden: set[str] | None = None, n: int = 8) -> str:
    """Runtime all-letter token that is not a named public sample."""
    blocked = set(forbidden or ())
    blocked.update({"ing", "run", "runn"})
    while True:
        raw = uuid.uuid4().hex
        tok = "".join("abcdefghijklmnop"[int(c, 16)] for c in raw[:n])
        if not tok.isalpha() or tok.endswith("ing") or tok in blocked:
            continue
        return tok


def _unsupported_language_name(*, extra: set[str] | None = None) -> str:
    blocked = set(SNOWBALL_LISTED)
    blocked.add("klingon")
    if extra:
        blocked.update(extra)
    while True:
        name = _alpha_token(forbidden=blocked, n=10)
        if name.isascii() and name not in blocked:
            return name


@contextmanager
def _empty_resources():
    """No packaged lists on the search list."""
    with workspace() as ws:
        with bound_resource_path(ws, present=False):
            yield ws


@contextmanager
def _stopwords_present(language: str, words: list[str]):
    """Install that language's list into the workspace search list."""
    with workspace() as ws:
        write_stopwords_list(ws, language, words)
        with bound_resource_path(ws, present=True):
            yield ws


def _porter():
    return require_constructed(call(PorterStemmer))


def _lancaster():
    return require_constructed(call(LancasterStemmer))


def _snowball(language: str, *, skip: bool = False):
    return require_constructed(
        call(SnowballStemmer, language, ignore_stopwords=skip)
    )


def _regexp(pattern: str):
    return require_constructed(call(RegexpStemmer, pattern))


def _ws_stripped(text: str) -> str:
    return "".join(text.split())


# ---------------------------------------------------------------------------
# A. Default Porter nineteen pairs and oed
# ---------------------------------------------------------------------------


def test_default_porter_nineteen_named_pairs():
    with _empty_resources():
        porter = _porter()
        got = [(word, stem_of(porter.stem, word)) for word, _expected in PORTER_PAIRS]
    print(f"default porter pairs={got!r}", flush=True)
    assert got == list(PORTER_PAIRS)


def test_default_porter_oed_succeeds_as_o():
    with _empty_resources():
        porter = _porter()
        got = stem_of(porter.stem, "oed")
    print(f"default porter oed={got!r}", flush=True)
    assert got == "o"


# ---------------------------------------------------------------------------
# B. Default Porter lowercases; the switch is distinguishable on I
# ---------------------------------------------------------------------------


def test_default_porter_running_case_matches():
    with _empty_resources():
        porter = _porter()
        upper = stem_of(porter.stem, "Running")
        lower = stem_of(porter.stem, "running")
    print(f"Running={upper!r} running={lower!r}", flush=True)
    assert upper == lower


def test_default_porter_runtime_capitalized_named_word_matches():
    word, expected = PORTER_PAIRS[0]
    capitalized = word[0].upper() + word[1:]
    with _empty_resources():
        porter = _porter()
        got = stem_of(porter.stem, capitalized)
        lower = stem_of(porter.stem, word)
    print(
        f"capitalized {capitalized!r} -> {got!r}; lower {word!r} -> {lower!r}",
        flush=True,
    )
    assert got == expected
    assert got == lower


def test_default_porter_I_lowercase_settings_differ():
    with _empty_resources():
        porter = _porter()
        on = stem_of(porter.stem, "I", to_lowercase=True)
        off = stem_of(porter.stem, "I", to_lowercase=False)
    print(f"I lowercase on={on!r} off={off!r}", flush=True)
    assert on == "i"
    assert off == "I"
    assert on != off


# ---------------------------------------------------------------------------
# C. Lancaster named pairs; distinguishable from Porter on maximum
# ---------------------------------------------------------------------------


def test_lancaster_named_pairs():
    with _empty_resources():
        lancaster = _lancaster()
        got = [
            (word, stem_of(lancaster.stem, word)) for word, _expected in LANCASTER_PAIRS
        ]
    print(f"lancaster pairs={got!r}", flush=True)
    assert got == list(LANCASTER_PAIRS)


def test_lancaster_maximum_is_maxim_default_porter_is_not():
    with _empty_resources():
        lanc = stem_of(_lancaster().stem, "maximum")
        port = stem_of(_porter().stem, "maximum")
    print(f"maximum lancaster={lanc!r} porter={port!r}", flush=True)
    assert lanc == "maxim"
    assert port != "maxim"


# ---------------------------------------------------------------------------
# D. Snowball english vs porter on generously
# ---------------------------------------------------------------------------


def test_snowball_english_running_and_generously():
    with _empty_resources():
        english = _snowball("english")
        running = stem_of(english.stem, "running")
        generously = stem_of(english.stem, "generously")
    print(f"english running={running!r} generously={generously!r}", flush=True)
    assert running == "run"
    assert generously == "generous"


def test_snowball_porter_generously_differs_from_english():
    with _empty_resources():
        english = stem_of(_snowball("english").stem, "generously")
        porter = stem_of(_snowball("porter").stem, "generously")
    print(f"generously english={english!r} porter={porter!r}", flush=True)
    assert english == "generous"
    assert porter == "gener"
    assert english != porter


# ---------------------------------------------------------------------------
# E. Snowball english stopword skipping and missing-list construction
# ---------------------------------------------------------------------------


def test_snowball_english_skip_off_having_without_wordlist():
    with _empty_resources():
        english = _snowball("english", skip=False)
        got = stem_of(english.stem, "having")
    print(f"english skip-off having (no list)={got!r}", flush=True)
    assert got == "have"


def test_snowball_english_skip_on_does_not_construct_without_wordlist():
    with _empty_resources():
        off = _snowball("english", skip=False)
        off_having = stem_of(off.stem, "having")
        on = call(SnowballStemmer, "english", ignore_stopwords=True)
        require_not_constructed(on)
    print(
        f"english skip-off having={off_having!r} skip-on exception={on.exception!r}",
        flush=True,
    )
    assert off_having == "have"
    assert on.exception is not None or not callable(getattr(on.value, "stem", None))


def test_snowball_english_skip_on_leaves_having_when_wordlist_present():
    with _stopwords_present("english", ["having"]):
        off = _snowball("english", skip=False)
        baseline = stem_of(off.stem, "having")
        on = _snowball("english", skip=True)
        skipped = stem_of(on.stem, "having")
    print(
        f"english list-present skip-off having={baseline!r} "
        f"skip-on having={skipped!r}",
        flush=True,
    )
    assert baseline == "have"
    assert skipped == "having"


# ---------------------------------------------------------------------------
# F. Snowball german named stems, skipping, and language-specific list
# ---------------------------------------------------------------------------


def test_snowball_german_schranke_and_skip_off_keinen_without_wordlist():
    with _empty_resources():
        german = _snowball("german", skip=False)
        schranke = stem_of(german.stem, "Schränke")
        keinen = stem_of(german.stem, "keinen")
    print(f"german skip-off Schränke={schranke!r} keinen={keinen!r}", flush=True)
    assert schranke == "schrank"
    assert keinen == "kein"


def test_snowball_german_skip_on_does_not_construct_without_wordlist():
    with _empty_resources():
        off = _snowball("german", skip=False)
        off_keinen = stem_of(off.stem, "keinen")
        on = call(SnowballStemmer, "german", ignore_stopwords=True)
        require_not_constructed(on)
    print(
        f"german skip-off keinen={off_keinen!r} skip-on exception={on.exception!r}",
        flush=True,
    )
    assert off_keinen == "kein"
    assert on.exception is not None or not callable(getattr(on.value, "stem", None))


def test_snowball_german_skip_on_leaves_keinen_when_wordlist_present():
    with _stopwords_present("german", ["keinen"]):
        off = _snowball("german", skip=False)
        baseline = stem_of(off.stem, "keinen")
        on = _snowball("german", skip=True)
        skipped = stem_of(on.stem, "keinen")
    print(
        f"german list-present skip-off keinen={baseline!r} "
        f"skip-on keinen={skipped!r}",
        flush=True,
    )
    assert baseline == "kein"
    assert skipped == "keinen"


def test_snowball_german_skip_on_fails_with_only_english_wordlist():
    other = _alpha_token(forbidden={"having", "have"})
    with _stopwords_present("english", ["having", other]):
        german_on = call(SnowballStemmer, "german", ignore_stopwords=True)
        require_not_constructed(german_on)
        english_off = stem_of(_snowball("english", skip=False).stem, "having")
        english_on = _snowball("english", skip=True)
        having_on = stem_of(english_on.stem, "having")
    print(
        f"english-list-only german skip-on exception={german_on.exception!r} "
        f"english skip-off having={english_off!r} skip-on having={having_on!r}",
        flush=True,
    )
    assert english_off == "have"
    assert having_on == "having"


# ---------------------------------------------------------------------------
# G. Snowball arabic / spanish / russian named pairs
# ---------------------------------------------------------------------------


def test_snowball_arabic_named_pairs():
    with _empty_resources():
        arabic = _snowball("arabic")
        got = [(word, stem_of(arabic.stem, word)) for word, _expected in ARABIC_PAIRS]
    print(f"arabic pairs={got!r}", flush=True)
    assert got == list(ARABIC_PAIRS)


def test_snowball_spanish_visionado():
    with _empty_resources():
        got = stem_of(_snowball("spanish").stem, "Visionado")
    print(f"spanish Visionado={got!r}", flush=True)
    assert got == "vision"


def test_snowball_russian_named_pair():
    with _empty_resources():
        got = stem_of(_snowball("russian").stem, "авантненькая")
    print(f"russian named={got!r}", flush=True)
    assert got == "авантненьк"


# ---------------------------------------------------------------------------
# H. Snowball language set: unsupported fails identifying; listed is usable
# ---------------------------------------------------------------------------


def test_snowball_klingon_fails_identifying_language_english_succeeds():
    with _empty_resources():
        english = _snowball("english")
        running = stem_of(english.stem, "running")
        failed = call(SnowballStemmer, "klingon")
        require_not_constructed(failed)
        obs = unsuccessful_observation(failed)
    print(f"english running={running!r} klingon obs={obs!r}", flush=True)
    assert running == "run"
    assert "klingon" in obs


def test_snowball_runtime_unsupported_language_is_identified():
    first = _unsupported_language_name()
    second = _unsupported_language_name(extra={first})
    with _empty_resources():
        a = call(SnowballStemmer, first)
        b = call(SnowballStemmer, second)
        require_not_constructed(a)
        require_not_constructed(b)
        obs_a = unsuccessful_observation(a)
        obs_b = unsuccessful_observation(b)
    print(f"unsupported {first!r} obs={obs_a!r} {second!r} obs={obs_b!r}", flush=True)
    assert first in obs_a
    assert second in obs_b
    assert obs_a != obs_b


def test_snowball_listed_language_without_named_stem_is_usable():
    word = _alpha_token()
    with _empty_resources():
        danish = _snowball("danish")
        got = stem_of(danish.stem, word)
        failed = call(SnowballStemmer, "klingon")
        require_not_constructed(failed)
    print(f"danish {word!r} -> {got!r} (str, unpinned)", flush=True)
    assert isinstance(got, str)


def test_snowball_ten_languages_named_pairs():
    """Each previously unpinned listed language has stems != the original word."""
    with _empty_resources():
        observed = {
            language: [
                (word, stem_of(_snowball(language).stem, word))
                for word, _expected in pairs
            ]
            for language, pairs in SNOWBALL_NAMED_PAIRS.items()
        }
    print(f"snowball named pairs={observed!r}", flush=True)
    for language, pairs in SNOWBALL_NAMED_PAIRS.items():
        got = observed[language]
        assert got == list(pairs), f"{language} stems {got!r} != {list(pairs)!r}"
        for word, stem in got:
            assert stem != word, f"{language} identity stem {word!r}"


# ---------------------------------------------------------------------------
# I. ARLSTem and ARLSTem2 exist; their stems are outside the specification,
# so only the shell is checked: each constructs and stem returns a str.
# ---------------------------------------------------------------------------


def test_arlstem_and_arlstem2_construct_and_stem_verb_to_str():
    with _empty_resources():
        one = stem_of(require_constructed(call(ARLSTem)).stem, "يعمل")
        two = stem_of(require_constructed(call(ARLSTem2)).stem, "يعمل")
    print(f"ARLSTem={one!r} ARLSTem2={two!r} (str, unpinned)", flush=True)
    assert isinstance(one, str)
    assert isinstance(two, str)


def test_arlstem_and_arlstem2_construct_and_stem_noun_to_str():
    with _empty_resources():
        one = stem_of(require_constructed(call(ARLSTem)).stem, "العربية")
        two = stem_of(require_constructed(call(ARLSTem2)).stem, "العربية")
    print(f"ARLSTem arabiyya={one!r} ARLSTem2={two!r} (str, unpinned)", flush=True)
    assert isinstance(one, str)
    assert isinstance(two, str)


# ---------------------------------------------------------------------------
# J. Suffix-pattern stemmer: caller pattern; trailing ing; not Porter
# ---------------------------------------------------------------------------


def test_regexp_strips_trailing_ing_from_running_not_snowball_english():
    with _empty_resources():
        rx = stem_of(_regexp(TRAILING_ING).stem, "running")
        snow = stem_of(_snowball("english").stem, "running")
    print(f"regexp running={rx!r} snowball english={snow!r}", flush=True)
    assert rx == "runn"
    assert snow == "run"
    assert rx != snow


def test_regexp_leaves_run_unchanged():
    with _empty_resources():
        got = stem_of(_regexp(TRAILING_ING).stem, "run")
    print(f"regexp run={got!r}", flush=True)
    assert got == "run"


def test_regexp_runtime_trailing_ing_stripped():
    tok = _alpha_token()
    word = tok + "ing"
    with _empty_resources():
        rx = _regexp(TRAILING_ING)
        stripped = stem_of(rx.stem, word)
        bare = stem_of(rx.stem, tok)
    print(f"regexp runtime {word!r} -> {stripped!r}; bare {tok!r} -> {bare!r}", flush=True)
    assert stripped == tok
    assert bare == tok


def test_regexp_ing_not_stripped_when_not_trailing():
    tok = _alpha_token()
    tail = _alpha_token(n=3)
    word = f"{tok}ing{tail}"
    with _empty_resources():
        got = stem_of(_regexp(TRAILING_ING).stem, word)
    print(f"regexp non-trailing {word!r} -> {got!r}", flush=True)
    assert got == word


def test_regexp_two_suffix_configs_differ_on_shared_word():
    tok = _alpha_token()
    while True:
        sfx = _alpha_token(n=4, forbidden={tok})
        if sfx == "ing" or tok.endswith(sfx):
            continue
        word = tok + sfx
        if word.endswith("ing"):
            continue
        break
    with _empty_resources():
        ing_cfg = _regexp(TRAILING_ING)
        sfx_cfg = _regexp(sfx + "$")
        from_ing = stem_of(ing_cfg.stem, word)
        from_sfx = stem_of(sfx_cfg.stem, word)
    print(
        f"shared {word!r} ing-cfg={from_ing!r} sfx-cfg={from_sfx!r} sfx={sfx!r}",
        flush=True,
    )
    assert from_sfx == tok
    assert from_ing != from_sfx


# ---------------------------------------------------------------------------
# K. Stemming is per word: a two-word string is one token
# ---------------------------------------------------------------------------


def test_default_porter_two_word_string_is_one_token():
    left = PORTER_PAIRS[1][0]
    right = PORTER_PAIRS[5][0]
    text = f"{left} {right}"
    with _empty_resources():
        porter = _porter()
        left_stem = stem_of(porter.stem, left)
        right_stem = stem_of(porter.stem, right)
        got = stem_of(porter.stem, text)
    stripped = _ws_stripped(got)
    live_left = _ws_stripped(left_stem)
    live_right = _ws_stripped(right_stem)
    live_join = live_left + live_right
    print(
        f"porter sentence {text!r} -> {got!r} stripped={stripped!r} "
        f"live={left_stem!r}+{right_stem!r} join={live_join!r}",
        flush=True,
    )
    assert isinstance(got, str)
    assert stripped != live_join
    assert stripped != live_left
    assert stripped != live_right


def test_lancaster_two_word_string_is_one_token():
    left = LANCASTER_PAIRS[3][0]
    right = LANCASTER_PAIRS[4][0]
    text = f"{left} {right}"
    with _empty_resources():
        lancaster = _lancaster()
        left_stem = stem_of(lancaster.stem, left)
        right_stem = stem_of(lancaster.stem, right)
        got = stem_of(lancaster.stem, text)
    stripped = _ws_stripped(got)
    live_left = _ws_stripped(left_stem)
    live_right = _ws_stripped(right_stem)
    live_join = live_left + live_right
    print(
        f"lancaster sentence {text!r} -> {got!r} stripped={stripped!r} "
        f"live={left_stem!r}+{right_stem!r} join={live_join!r}",
        flush=True,
    )
    assert isinstance(got, str)
    assert stripped != live_join
    assert stripped != live_left
    assert stripped != live_right


# ---------------------------------------------------------------------------
# L. Missing WordNet fails the lemmatizer; graded stemmers still succeed
# ---------------------------------------------------------------------------


def test_wordnet_lemmatizer_fails_without_wordnet_graded_stemmers_do_not():
    word = "caresses"
    with _empty_resources():
        ctor = call(WordNetLemmatizer)
        if ctor.exception is not None:
            require_no_lemma(ctor)
        else:
            require_no_lemma(call(ctor.value.lemmatize, word))
        porter = stem_of(_porter().stem, "caresses")
        lancaster = stem_of(_lancaster().stem, "maximum")
        english = stem_of(_snowball("english", skip=False).stem, "running")
    print(
        f"graded still succeed porter={porter!r} lancaster={lancaster!r} "
        f"english={english!r}",
        flush=True,
    )
    assert porter == "caress"
    assert lancaster == "maxim"
    assert english == "run"


# ---------------------------------------------------------------------------
# M. Isolated subprocess: loaded library yields the named Porter stem
# ---------------------------------------------------------------------------


def test_default_porter_stems_in_isolated_subprocess():
    probe = (
        "from lingora.stem import PorterStemmer\n"
        "print('STEM=' + repr(PorterStemmer().stem('caresses')))\n"
    )
    present = run_python(code=probe, include_product=True)
    print(
        f"present rc={present.returncode} out={present.stdout!r} err={present.stderr!r}",
        flush=True,
    )
    assert "STEM='caress'" in present.stdout_text
