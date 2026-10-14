# feature: F01
"""Observation helpers for the detector-command report (FP-01).

Every public observation goes through ``_harness.invoke``. Helpers read
the report, error, usage, and switch forms the Interface Contract states
for ``scripts/detect.py`` (``_metrics`` member names, ``<N>_<slug>`` finding
keys, the ``error`` object, exit statuses, literal switch spellings).
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from _harness import (
    HarnessError,
    RunResult,
    invoke,
    workspace,
)

# ---------------------------------------------------------------------------
# Catalogue titles (PRD L100) and named splits (L96, L99, L102, L104)
# ---------------------------------------------------------------------------

CATALOGUE_TITLES: dict[int, str] = {
    1: "AI vocabulary",
    2: "model-dialect vocabulary",
    3: "promotional language",
    4: "hyphenated word-pair overuse",
    5: '"simple yet X" cliché',
    6: "stacked adjective chains",
    7: "rule of three overuse",
    8: "synonym cycling",
    9: "generic character naming in fiction",
    10: "significance inflation",
    11: "notability name-dropping",
    12: "vague attributions",
    13: "article-titles-as-proper-nouns",
    14: "conservation / ecosystem padding",
    15: "false ranges",
    16: "superficial -ing tail clauses",
    17: "negative parallelisms and tailing negations",
    18: '"Not X, just Y" / "No X, just Y"',
    19: "filler phrases",
    20: "empty pivot phrases",
    21: "outcome speculation tails",
    22: "persuasive authority tropes",
    23: "editorial interjections",
    24: "self-thoroughness phrases",
    25: "question-answer rhetorical pattern",
    26: '"concrete evidence" defense phrase',
    27: "compulsive intro hooks",
    28: "meandering intro",
    29: "prompt echo",
    30: "diff-anchored writing",
    31: "signposting and announcements",
    32: "cataloguing lead-ins",
    33: "inline-header vertical lists",
    34: "mid-essay bullet injection",
    35: "fragmented headers",
    36: "formulaic challenges sections",
    37: "transition cluster overuse",
    38: "compulsive conclusion phrases",
    39: "generic positive conclusions",
    40: "sentence-length monotony",
    41: "mechanical sentence-length alternation",
    42: "opener repetition",
    43: "avoidance of fragments and run-ons",
    44: "uniform paragraph length",
    45: "identical paragraph structure",
    46: "semicolon and parenthesis underuse",
    47: "chatbot artifacts",
    48: "sycophantic / servile tone",
    49: "RLHF / helpful-assistant register",
    50: "knowledge-cutoff disclaimers",
    51: "copula avoidance",
    52: "passive voice and subjectless fragments",
    53: "two-way passive-voice drift",
    54: "excessive hedging",
    55: "contraction absence",
    56: "boldface overuse",
    57: "emojis",
    58: "em-dash overuse",
    59: "title case in headings",
    60: "curly quotation marks",
    61: "hyphen-for-en-dash in numeric ranges",
    62: "invisible / zero-width characters",
    63: "placeholder / Mad-Libs text",
    64: "chatbot reference-markup leak",
    65: "AI tracking params",
    66: "homoglyph / mixed-script confusables",
    67: "non-standard spaces",
    68: "trailing / stray whitespace",
    69: "canonical marketing-slop phrases",
    70: "decorative horizontal rules",
    71: "degenerate repetition",
}


NO_DETECTOR: frozenset[int] = frozenset({7, 9, 28, 29, 43, 45, 49, 52, 53})
WRITING_ADVICE: frozenset[int] = frozenset(
    {4, 19, 22, 41, 42, 46, 54, 55, 58, 60, 61, 68}
)
DECISIVE: frozenset[int] = frozenset({62, 63, 64, 65, 66, 13, 47, 50, 48})
RHYTHM_CLASS: frozenset[int] = frozenset({40, 41, 44, 55})
# L104 score-moving rhythm carrier. 41 and 55 are advice (weight zero).
RHYTHM_SCORE_MOVING: frozenset[int] = frozenset({40, 44})
BAND_RANGES: dict[str, tuple[int, int]] = {
    "clean": (0, 20),
    "light tells": (21, 40),
    "mixed": (41, 60),
    "heavy tells": (61, 80),
    "pervasive tells": (81, 100),
}
CONFIDENCE_LABELS: frozenset[str] = frozenset({"none", "low", "moderate", "high"})
SCAN_CAP = 262144

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "to",
        "for",
        "with",
        "as",
        "is",
        "it",
        "at",
        "by",
        "from",
    }
)

# ---------------------------------------------------------------------------
# Stated shell of the detector command (Interface Contract, scripts/detect.py)
# ---------------------------------------------------------------------------

METRICS_KEY = "_metrics"
SCORE_KEY = "ai_tell_score"
BAND_KEY = "ai_tell_band"
CONFIDENCE_KEY = "confidence"
REASON_KEY = "confidence_reason"
SCANNED_KEY = "scanned_chars"
TRUNCATED_KEY = "truncated"
FLAGGED_KEY = "patterns_flagged"
INVISIBLE_KEY = "invisible_chars"
SPACE_KEY = "nonstandard_spaces"
MIXED_KEY = "homoglyphs"
INTERVAL_KEY = "score_ci"
INTERVAL_NOTE_KEY = "score_ci_note"
FINDING_KEY_RE = re.compile(r"^([1-9][0-9]*)_(.+)$")
FINDING_LABEL = "label"
FINDING_COUNT = "count"
FINDING_SAMPLES = "samples"

CLEANUP_FLAG = "--clean"
INTERVAL_FLAG = "--ci"
HELP_FLAG = "--help"
HELP_SHORT = "-h"
END_OF_OPTIONS = "--"
USAGE_SYNOPSIS = "usage: detect.py [--clean] [--ci] [--] [FILE]"

ERROR_KEY = "error"
EMPTY_INPUT_ERROR = "empty input"
UNREADABLE_ERROR_PREFIX = "cannot read input:"
UNKNOWN_OPTION_WORDS = "unknown option"
EXIT_EMPTY_INPUT = 1
EXIT_UNREADABLE = 1
EXIT_UNKNOWN_OPTION = 2

# Stated member paths (kept for helpers in other features that address a
# metric by path).
_PATHS: dict[str, tuple] = {
    "score": (SCORE_KEY,),
    "band": (BAND_KEY,),
    "confidence": (CONFIDENCE_KEY,),
    "scanned": (SCANNED_KEY,),
    "truncated": (TRUNCATED_KEY,),
    "window_mark": (TRUNCATED_KEY,),
    "invisible": (INVISIBLE_KEY,),
    "space": (SPACE_KEY,),
    "mixed": (MIXED_KEY,),
}

CORE_SLOTS: tuple[str, ...] = ("score", "band", "confidence", "scanned")


@contextmanager
def binding(*slots: str) -> Iterator[None]:
    """Former module-setup binding step. Members are stated by name now, so a
    validation failure here is only logged; every reader checks its member
    directly inside the test that reads it."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - readers re-check per test
        print(f"[bind] {slots!r} validation: {type(exc).__name__}: {str(exc)[:600]}", flush=True)



# ---------------------------------------------------------------------------
# PRD-quoted probes plus runtime twins (anti-memorization)
# ---------------------------------------------------------------------------

SHORT_FACTUAL = (
    "Balsa is a fast-growing tree native to Central and South America. Its wood is "
    "light because the cells are large and thin-walled. A cubic metre of dried balsa "
    "weighs about 160 kilograms, roughly a fifth of oak."
)

SHORT_FACTUAL_TWIN = (
    "Oak is a slow-growing tree native to temperate northern forests. Its wood is "
    "dense because the cells are small and thick-walled. A cubic metre of dried oak "
    "weighs about eight hundred kilograms, far more than balsa."
)

SHORT_SLOP = (
    "In today's fast-paced world, leveraging cutting-edge solutions is essential. By "
    "fostering collaboration and driving innovation, teams unlock unprecedented value. "
    "Ultimately, the possibilities are endless."
)

SHORT_SLOP_TWIN = (
    "In this shifting digital landscape, showcasing robust solutions is essential. By "
    "fostering collaboration and elevating innovation, teams unlock unprecedented value. "
    "Ultimately, the possibilities are endless."
)

HUMANIZED_CODING = """\
AI coding assistants can make you faster at the boring parts. Not everything. Definitely not architecture.

They're great at boilerplate: config files, test scaffolding, repetitive refactors. They're also great at sounding right while being wrong. I've accepted suggestions that compiled, passed lint, and still missed the point because I stopped paying attention.

People I talk to land in two camps. Some use it like autocomplete for chores and review every line. Others disable it after it keeps suggesting patterns they don't want.
"""

AI_REGISTER = """\
Certainly! Below is an overview of the topic. Great question, by the way.

Urban beekeeping stands as a compelling testament to the transformative power of community stewardship, marking a pivotal chapter in how cities reimagine their relationship with the natural world. Across today's rapidly shifting urban landscape, these vibrant rooftop apiaries are reshaping how residents cultivate, harvest, and connect, underscoring their crucial role in a robust local food ecosystem.

At its core, the appeal is multifaceted: fostering biodiversity, empowering neighbourhoods, and unlocking a deeper appreciation of pollinators. It is not merely a hobby; it is a movement that leverages small spaces for outsized impact.

While specific details are limited based on available information, it could potentially possibly be argued that such initiatives might have some measurable benefit. Despite challenges typical of emerging practices, the community continues to thrive. In order to fully realize this potential, participants must align with established best practices.

In conclusion, the outlook is bright. Exciting times lie ahead as we delve deeper into this rewarding journey. Let me know if you would like me to expand on any section!
"""

OPENER_BLOCK = (
    "The system handles authentication. The system caches sessions for one "
    "hour after each successful login at the east quay office near the lock. "
    "The system rotates keys daily."
)

HEDGE_STACK = "The policy could possibly affect outcomes somewhat."

# Writing-advice probes (L19 / L99). Phrases are the named pattern kinds, not
# product key spellings.
HYPHENATED_CLICHE_PAIRS = (
    "The lock used cutting-edge hardware and a state-of-the-art gate."
)
FILLER_PHRASES = (
    "Due to the fact that the lock opened at dawn, crews stood by in order to pass the barges."
)
AUTHORITY_TROPES = (
    "At the end of the day the lock still opens and the bottom line is the gates meet the sill."
)
EM_DASH_OVERUSE = (
    "The lock — rebuilt after the flood — still opens at dawn — even in frost."
)
CURLY_QUOTES = (
    "The keeper said “the lock opened at dawn after the flood.”"
)
HYPHEN_NUMERIC_RANGE = (
    "The survey covers 2010-2015 along the eastern wall of the lock."
)
PARALLELISM_FORM_17 = (
    "The lock is not only a gate but also a measuring pond on the river."
)
# L108 / L126 named parallelism-form 17 fire. Distinct from catalogue 18.
RESIN_PARALLELISM_17 = (
    "It's not just about the resin holding the fibres in place; it's about "
    "how the laminate fails under load"
)
# Same prose with the parallelism phrasing removed (L108 / L126 score oracle).
RESIN_WITHOUT_PARALLELISM = (
    "The resin holding the fibres in place. How the laminate fails under load."
)
TAILING_NEGATION_17 = (
    "The joint is tight, no wasted motion in the crew's work."
)
# Same prose with the named comma-plus-"no wasted motion" tail removed (L108).
TAILING_NEGATION_WITHOUT = (
    "The joint is tight in the crew's work."
)
# Isolated AI-vocabulary in ordinary prose (L101). Short enough that adding
# the named chatbot-artifact probe takes the two-family floor of 25; the
# isolated integer itself is at most 40, not capped below 25.
ISOLATED_DELVE = (
    "They delve into the old parish records after the flood receded."
)
# L104 / L126 named three-sentence snow-and-road rhythm-only document.
SNOW_AND_ROAD = (
    "Snow covered the high passes. Trucks waited below the ridge. "
    "Crews cleared the road slowly."
)
CONTRACTABLE_OPINION = (
    "I am certain I have seen the lock and I will not pretend I cannot tell. "
    "I do not know the year and I am ready because I have time and I will wait and I cannot rush."
)
CONTRACTED_OPINION = (
    "I'm certain I've seen the lock and I won't pretend I can't tell. "
    "I don't know the year and I'm ready because I've time and I'll wait and I can't rush."
)
# L108 constructable fires: comma plus underscoring (16); TAG-block (62).
UNDERSCOPING_16 = "The beam sits true, underscoring the old scarf joint."
# Unicode TAG block (U+E0000–U+E007F) inside English prose. Not a product key.
TAG_BLOCK_62 = (
    "Hidden" + chr(0xE0041) + chr(0xE0049) + "word in English prose near the lock."
)
NOT_JUST_18 = (
    "It's not just a hobby, it's a craft. No fluff, just results on the quay."
)

PLACEHOLDER = "[Your Name]"
PLACEHOLDER_TWIN = "[INSERT EMAIL]"
TRACKING_URL = "https://example.com/post?utm_source=chatgpt.com"
TRACKING_URL_PERIOD = "https://x.com/a?utm_source=chatgpt.com."
TRACKING_URL_TWIN = "https://docs.example.net/note?utm_source=chatgpt.com"
TRACKING_OTHER_DOMAIN = "https://x.com/a?utm_source=chatgpt.com.au"

VOCAB_STACK = "delve tapestry pivotal showcase seamless"
# L108 named AI-vocabulary fire. One family; not a one-family integer cap
# below 25 and not a vocab-only exit from clean / light tells.
STACKED_VOCAB_FIRE = "They delve tapestry pivotal showcase seamless in one line."


# ---------------------------------------------------------------------------
# Small text utilities
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r'["“”/_,:;!.?()\[\]{}]', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        tok
        for tok in _norm(text).split()
        if tok and tok not in _STOP and len(tok) > 1
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Findings (Contract: one top-level member per fired finding, key
# ``<N>_<slug>``; value {label, count, samples})
# ---------------------------------------------------------------------------


def _check(cond: bool, message: str) -> None:
    """Reader failure: the stated member is missing or not of its stated type."""
    if not cond:
        raise HarnessError(message)


def finding_number(key: Any) -> int:
    """Catalogue number named by a finding member's key (``<N>_<slug>``)."""
    match = FINDING_KEY_RE.match(str(key))
    _check(match is not None, (
        f"report member {key!r} is neither {METRICS_KEY!r} nor a finding key "
        f"of the form <N>_<slug>"
    ))
    return int(match.group(1))


def _finding_entries(findings: Any) -> list[Any]:
    if isinstance(findings, Mapping):
        return list(findings.values())
    raise HarnessError(f"findings are {type(findings).__name__}, not an object")


def _as_finding(item: Any, key: Any = None) -> dict[str, Any]:
    """Read one finding value by its stated member names."""
    if isinstance(item, Mapping) and "raw" in item and "hit" in item:
        return dict(item)
    _check(isinstance(item, Mapping), f"finding is {type(item).__name__}, not an object")
    label = item.get(FINDING_LABEL)
    _check(isinstance(label, str) and bool(label.strip()), (
        f"finding {key!r} has no non-empty {FINDING_LABEL!r} string: {item!r}"
    ))
    count = item.get(FINDING_COUNT)
    _check(_is_int(count) and count >= 1, (
        f"finding {key!r} {FINDING_COUNT!r} is not a positive integer: {item!r}"
    ))
    samples = item.get(FINDING_SAMPLES)
    _check(isinstance(samples, list) and all(isinstance(s, str) for s in samples), (
        f"finding {key!r} {FINDING_SAMPLES!r} is not an array of strings: {item!r}"
    ))
    _check(len(samples) <= 3, (
        f"finding {key!r} sample list length {len(samples)} exceeds the cap of 3"
    ))
    number = finding_number(key) if key is not None else None
    return {
        "number": number,
        "key": key,
        "label": label,
        "hit": count,
        "samples": list(samples),
        "raw": item,
    }


def hit_count(finding: Any) -> int:
    return int(_as_finding(finding)["hit"])


def sample_list(finding: Any) -> list[str]:
    return list(_as_finding(finding)["samples"])


def _strip_cut_marks(sample: str) -> str:
    out = sample.strip()
    for mark in ("...", "…"):
        if out.startswith(mark):
            out = out[len(mark):]
        if out.endswith(mark):
            out = out[: -len(mark)]
    return out.strip()


def samples_drawn_from(samples: Sequence[str], text: str) -> None:
    """Contract: an AI-vocabulary (1) sample is a contiguous excerpt of the
    scanned text; line breaks may appear as spaces, and either end may carry
    a ``...`` / ``…`` cut mark. An empty list is within "up to three"."""
    flat = re.sub(r"\s+", " ", text)
    for sample in samples:
        assert isinstance(sample, str) and sample.strip(), f"sample is empty: {sample!r}"
        core = re.sub(r"\s+", " ", _strip_cut_marks(sample))
        assert core, f"sample has no text besides cut marks: {sample!r}"
        assert core in flat, (
            f"sample {sample!r} is not an excerpt of the scanned text"
        )


def _records(findings: Any) -> list[dict[str, Any]]:
    if not isinstance(findings, Mapping):
        raise HarnessError(f"findings are {type(findings).__name__}, not an object")
    return [_as_finding(value, key) for key, value in findings.items()]


def catalogue_numbers(findings: Any) -> set[int]:
    return {rec["number"] for rec in _records(findings)}


def require_finding(findings: Any, number: int) -> dict[str, Any]:
    matched = [rec for rec in _records(findings) if rec["number"] == number]
    assert matched, (
        f"catalogue {number} ({CATALOGUE_TITLES[number]}) did not fire; "
        f"present={sorted(catalogue_numbers(findings))}"
    )
    return matched[0]


def require_absent_finding(findings: Any, number: int) -> None:
    matched = [rec for rec in _records(findings) if rec["number"] == number]
    assert not matched, (
        f"catalogue {number} ({CATALOGUE_TITLES[number]}) fired unexpectedly: "
        f"{matched[0]['key']!r}"
    )


# Contract: catalogue 17's two forms are reported as their own members.
PARALLELISM_17_KEY = "17_negative_parallelism"
TAILING_17_KEY = "17_tailing_negation"


def require_member(findings: Any, key: str) -> dict[str, Any]:
    """The finding member with this stated key is present."""
    if not isinstance(findings, Mapping):
        raise HarnessError(f"findings are {type(findings).__name__}, not an object")
    assert key in findings, f"finding member {key!r} absent; present={sorted(findings)}"
    return _as_finding(findings[key], key)


def require_absent_member(findings: Any, key: str) -> None:
    """The finding member with this stated key is absent."""
    if not isinstance(findings, Mapping):
        raise HarnessError(f"findings are {type(findings).__name__}, not an object")
    assert key not in findings, f"finding member {key!r} present unexpectedly"


def finding_records(findings: Any) -> list[dict[str, Any]]:
    """Finding records: number (from the key), label, hit (count), samples."""
    return _records(findings)


def score_moving_numbers(findings: Any) -> set[int]:
    """Catalogue numbers outside the twelve writing-advice numbers."""
    return catalogue_numbers(findings) - WRITING_ADVICE


# ---------------------------------------------------------------------------
# Metrics (Contract: ``_metrics`` members by name)
# ---------------------------------------------------------------------------


def _member(metrics: Mapping[str, Any], name: str) -> Any:
    _check(isinstance(metrics, Mapping), f"metrics are not an object: {metrics!r}")
    _check(name in metrics, f"{METRICS_KEY} has no member {name!r}")
    return metrics[name]


def band_of(metrics: Mapping[str, Any]) -> str:
    value = _member(metrics, BAND_KEY)
    _check(value in BAND_RANGES, f"{BAND_KEY} is not a band name: {value!r}")
    return str(value)


def confidence_of(metrics: Mapping[str, Any]) -> str:
    value = _member(metrics, CONFIDENCE_KEY)
    _check(value in CONFIDENCE_LABELS, f"{CONFIDENCE_KEY} is not a confidence word: {value!r}")
    return str(value)


def reason_of(metrics: Mapping[str, Any]) -> str:
    """``confidence_reason``: non-empty when confidence is not high (wording free)."""
    conf = confidence_of(metrics)
    value = _member(metrics, REASON_KEY)
    _check(isinstance(value, str), f"{REASON_KEY} is not a string: {value!r}")
    if conf != "high":
        _check(value.strip(), f"confidence {conf!r} has an empty {REASON_KEY}")
    return value


def scanned_of(metrics: Mapping[str, Any], *, chars: int | None = None) -> int:
    value = _member(metrics, SCANNED_KEY)
    _check(_is_int(value), f"{SCANNED_KEY} is not an integer: {value!r}")
    _check(0 <= value <= SCAN_CAP, f"{SCANNED_KEY} {value} is outside 0..{SCAN_CAP}")
    return value


def score_of(
    metrics: Mapping[str, Any],
    *,
    findings: Any | None = None,
) -> int:
    value = _member(metrics, SCORE_KEY)
    _check(_is_int(value), f"{SCORE_KEY} is not an integer: {value!r}")
    _check(0 <= value <= 100, f"{SCORE_KEY} {value} is outside 0-100")
    return value


def finding_count_of(metrics: Mapping[str, Any], findings: Any) -> int:
    value = _member(metrics, FLAGGED_KEY)
    _check(_is_int(value), f"{FLAGGED_KEY} is not an integer: {value!r}")
    assert value == len(_finding_entries(findings)), (
        f"{FLAGGED_KEY}={value} but the report has "
        f"{len(_finding_entries(findings))} finding members"
    )
    return value


def assert_band_agrees_with_score(
    metrics: Mapping[str, Any], *, findings: Any | None = None
) -> None:
    band = band_of(metrics)
    score = score_of(metrics, findings=findings)
    lo, hi = BAND_RANGES[band]
    assert lo <= score <= hi, (
        f"band {band!r} does not contain score {score} (range {lo}-{hi})"
    )


def _count_member(metrics: Mapping[str, Any], name: str) -> int:
    value = _member(metrics, name)
    _check(_is_int(value) and value >= 0, f"{name} is not a non-negative integer: {value!r}")
    return value


def invisible_count_of(metrics: Mapping[str, Any]) -> int:
    return _count_member(metrics, INVISIBLE_KEY)


def nonstandard_space_count_of(metrics: Mapping[str, Any]) -> int:
    return _count_member(metrics, SPACE_KEY)


def mixed_script_count_of(metrics: Mapping[str, Any]) -> int:
    return _count_member(metrics, MIXED_KEY)


def require_character_layer_counts(
    metrics: Mapping[str, Any],
) -> tuple[int, int, int]:
    """Metrics always include the three character-layer counts."""
    return (
        invisible_count_of(metrics),
        nonstandard_space_count_of(metrics),
        mixed_script_count_of(metrics),
    )


def truncated_of(metrics: Mapping[str, Any]) -> bool:
    """``truncated``: false = not longer than the window, true = longer."""
    value = _member(metrics, TRUNCATED_KEY)
    _check(isinstance(value, bool), f"{TRUNCATED_KEY} is not a boolean: {value!r}")
    return value


def window_mark_of(metrics: Mapping[str, Any]) -> Any:
    return truncated_of(metrics)


def window_is_longer(metrics: Mapping[str, Any]) -> bool:
    return truncated_of(metrics) is True


def window_is_not_longer(metrics: Mapping[str, Any]) -> bool:
    return truncated_of(metrics) is False


def _require_core_members(metrics: Mapping[str, Any]) -> None:
    score_of(metrics)
    band_of(metrics)
    confidence_of(metrics)
    reason_of(metrics)
    scanned_of(metrics)
    truncated_of(metrics)
    require_character_layer_counts(metrics)


# Former contrast "binding" steps. The member names are stated in the
# Interface Contract, so these only validate that the stated members are
# present on the reports they are given.


def bind_core_metric_paths(
    low_metrics: Mapping[str, Any],
    high_metrics: Mapping[str, Any],
    *,
    none_metrics: Mapping[str, Any] | None = None,
    high_conf_metrics: Mapping[str, Any] | None = None,
    scanned_metrics: Mapping[str, Any] | None = None,
    scanned_chars: int | None = None,
    scanned_over_metrics: Mapping[str, Any] | None = None,
) -> None:
    for blob in (low_metrics, high_metrics, none_metrics, high_conf_metrics,
                 scanned_metrics, scanned_over_metrics):
        if blob is not None:
            _require_core_members(blob)


def bind_invisible_count(baseline_metrics, extra_metrics) -> None:
    invisible_count_of(baseline_metrics)
    invisible_count_of(extra_metrics)


def bind_nonstandard_space_count(baseline_metrics, extra_metrics) -> None:
    nonstandard_space_count_of(baseline_metrics)
    nonstandard_space_count_of(extra_metrics)


def bind_mixed_script_count(baseline_metrics, extra_metrics) -> None:
    mixed_script_count_of(baseline_metrics)
    mixed_script_count_of(extra_metrics)


def bind_truncated_mark(at_metrics, over_metrics) -> None:
    truncated_of(at_metrics)
    truncated_of(over_metrics)


def bind_window_mark(at_metrics, over_metrics, extra_over_metrics, not_longer_metrics) -> None:
    for blob in (at_metrics, over_metrics, extra_over_metrics, not_longer_metrics):
        truncated_of(blob)


# ---------------------------------------------------------------------------
# Interval (Contract: ``score_ci`` only with ``--ci``)
# ---------------------------------------------------------------------------


def interval_pair(metrics: Mapping[str, Any], score: int | None = None) -> tuple[float, float] | None:
    """``score_ci`` as (low, high), or None when absent or null."""
    if INTERVAL_KEY not in metrics or metrics[INTERVAL_KEY] is None:
        return None
    value = metrics[INTERVAL_KEY]
    _check(
        isinstance(value, list)
        and len(value) == 2
        and all(_is_number(v) for v in value),
        f"{INTERVAL_KEY} is not [low, high]: {value!r}",
    )
    low, high = float(value[0]), float(value[1])
    _check(0 <= low <= high <= 100, f"{INTERVAL_KEY} is not an ordered 0-100 pair: {value!r}")
    return (low, high)


def interval_present(metrics: Mapping[str, Any], score: int | None = None) -> bool:
    return interval_pair(metrics, score) is not None


def too_few_sentences_stated(metrics: Mapping[str, Any]) -> None:
    """With ``--ci`` and fewer than four sentences: ``score_ci`` is null and
    ``score_ci_note`` is a string (its wording is free)."""
    assert INTERVAL_KEY in metrics, (
        f"interval switch was given but {METRICS_KEY} has no {INTERVAL_KEY!r} member"
    )
    assert metrics[INTERVAL_KEY] is None, (
        f"{INTERVAL_KEY} is not null on a document with too few sentences: "
        f"{metrics[INTERVAL_KEY]!r}"
    )
    note = metrics.get(INTERVAL_NOTE_KEY)
    assert isinstance(note, str), f"{INTERVAL_NOTE_KEY} is not a string: {note!r}"


def advice_does_not_move_score(base: str, extra: str, number: int) -> set[int]:
    """Extra arm reports writing-advice *number* and does not move the score."""
    b_f, b_m = require_success_report(scan_stdin(base), input_chars=unicode_len(base))
    e_f, e_m = require_success_report(scan_stdin(extra), input_chars=unicode_len(extra))
    require_finding(e_f, number)
    moving_b = score_moving_numbers(b_f)
    moving_e = score_moving_numbers(e_f)
    print(
        f"[F01] advice {number} moving_b={sorted(moving_b)} moving_e={sorted(moving_e)}",
        flush=True,
    )
    assert moving_b == moving_e, (
        f"writing-advice {number} changed the score-moving family set: "
        f"{sorted(moving_b)} -> {sorted(moving_e)}"
    )
    b_score = score_of(b_m, findings=b_f)
    e_score = score_of(e_m, findings=e_f)
    assert b_score == e_score, (
        f"writing-advice {number} moved the score from {b_score} to {e_score}"
    )
    return catalogue_numbers(e_f) & WRITING_ADVICE


# ---------------------------------------------------------------------------
# Success / failure carriers
# ---------------------------------------------------------------------------


def parse_structured_mapping(text: str, *, source: str) -> dict[str, Any]:
    """Read *text* as one JSON object (the Contract's report encoding)."""
    stripped = text.strip()
    if not stripped:
        raise HarnessError(f"{source} is empty; expected one JSON object")
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        excerpt = stripped if len(stripped) <= 500 else stripped[:500] + "…"
        raise HarnessError(f"{source} is not one JSON object ({exc}); text={excerpt!r}") from exc
    if not isinstance(obj, dict):
        raise HarnessError(f"{source} is JSON {type(obj).__name__}, not an object")
    return obj


def metrics_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """The report's ``_metrics`` member."""
    if not isinstance(report, Mapping):
        raise HarnessError(f"structured report is {type(report).__name__}, not an object")
    metrics = report.get(METRICS_KEY)
    _check(isinstance(metrics, Mapping), (
        f"report has no {METRICS_KEY!r} object; members={sorted(report)!r}"
    ))
    return metrics  # type: ignore[return-value]


def findings_from_report(report: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every report member other than ``_metrics``; each key is ``<N>_<slug>``."""
    if not isinstance(report, Mapping):
        raise HarnessError(f"structured report is {type(report).__name__}, not an object")
    entries: dict[str, Any] = {}
    for key, value in report.items():
        if key == METRICS_KEY:
            continue
        finding_number(key)
        entries[str(key)] = value
    return entries


def structured_report(result: RunResult) -> dict[str, Any]:
    """Parse detector stdout as the JSON report."""
    try:
        return parse_structured_mapping(result.stdout_text, source="detector stdout")
    except HarnessError as exc:
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={result.stderr_text!r}"
        ) from exc


def structured_error_mapping(result: RunResult) -> dict[str, Any]:
    """The last non-empty stderr line, read as ``{"error": <string>}``."""
    lines = [ln for ln in result.stderr_text.splitlines() if ln.strip()]
    assert lines, (
        f"error stream is empty; expected a JSON error object; "
        f"exit={result.returncode}; stdout={result.stdout_text!r}"
    )
    try:
        obj = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"last error-stream line is not a JSON object: {lines[-1]!r} ({exc})"
        ) from exc
    assert isinstance(obj, dict), f"error line is JSON {type(obj).__name__}, not an object"
    assert isinstance(obj.get(ERROR_KEY), str), (
        f"error object has no string {ERROR_KEY!r} member: {obj!r}"
    )
    return obj


def failure_record(result: RunResult) -> str:
    """The ``error`` string of the structured error."""
    return str(structured_error_mapping(result)[ERROR_KEY])


def error_points_toward_help(record: str, usage: str = "") -> None:
    """Unknown-option error text contains ``--help``."""
    assert HELP_FLAG in record, (
        f"unknown-option error does not point at {HELP_FLAG}: {record!r}"
    )


def _looks_like_frames(text: str) -> bool:
    lines = text.splitlines()
    frameish = 0
    for line in lines:
        if re.match(r"\s+File\s+", line):
            frameish += 1
        elif re.match(r"\s+at\s+\S+", line):
            frameish += 1
        elif re.match(r"\s+\^+\s*$", line):
            frameish += 1
    return frameish >= 2 or "Traceback (most recent call last)" in text


def require_no_traceback(result: RunResult) -> None:
    """The error stream carries no traceback / multi-frame dump."""
    text = result.stderr_text
    assert not _looks_like_frames(text), f"error stream carries a traceback: {text!r}"


def require_success_report(
    result: RunResult, *, input_chars: int | None = None
) -> tuple[Any, dict[str, Any]]:
    """Exit 0 and one JSON report whose stated members all read correctly."""
    assert result.returncode == 0, (
        f"expected success, got exit {result.returncode}; "
        f"stderr={result.stderr_text!r}"
    )
    report = structured_report(result)
    metrics = metrics_from_report(report)
    findings = findings_from_report(report, metrics)
    records = _records(findings)
    band = band_of(metrics)
    conf = confidence_of(metrics)
    reason_of(metrics)
    scanned = scanned_of(metrics)
    if input_chars is not None:
        assert scanned == min(input_chars, SCAN_CAP), (
            f"{SCANNED_KEY}={scanned}, expected {min(input_chars, SCAN_CAP)} "
            f"for {input_chars} characters"
        )
    finding_count_of(metrics, findings)
    score = score_of(metrics, findings=findings)
    assert_band_agrees_with_score(metrics, findings=findings)
    require_character_layer_counts(metrics)
    truncated_of(metrics)
    print(
        f"[F01] success score={score} band={band!r} confidence={conf!r} "
        f"scanned={scanned} findings={sorted(r['number'] for r in records)}",
        flush=True,
    )
    return findings, metrics


def require_structured_failure(result: RunResult) -> str:
    """Non-zero exit, empty stdout, JSON error object on stderr, no traceback."""
    assert result.returncode != 0, (
        f"expected failing status, got success; stdout={result.stdout_text!r}"
    )
    require_no_traceback(result)
    err = failure_record(result)
    assert not result.stdout.strip(), (
        f"failure printed on standard output: {result.stdout_text[:300]!r}"
    )
    print(f"[F01] failure exit={result.returncode} error={err!r}", flush=True)
    return err


def strip_error_covariates(record: str, *tokens: str) -> str:
    text = record
    for token in tokens:
        if not token:
            continue
        text = text.replace(token, "")
        text = text.replace(json.dumps(token)[1:-1], "")
    return re.sub(r"\s+", " ", text).strip()


def strip_paths_from_stderr(text: str, *paths: str) -> str:
    out = text
    for path in paths:
        if not path:
            continue
        out = out.replace(path, "")
        out = out.replace(str(path).replace("\\", "/"), "")
    return re.sub(r"\s+", " ", out).strip()


def is_empty_input_error(record: str) -> bool:
    return record.strip() == EMPTY_INPUT_ERROR


def is_unreadable_error(record: str) -> bool:
    return record.strip().startswith(UNREADABLE_ERROR_PREFIX)


def empty_input_identity(
    empty_records: Sequence[str], contrast_records: Sequence[str]
) -> None:
    """Empty extracted prose: ``error`` is exactly ``empty input``; the other
    failure kinds are not."""
    for rec in empty_records:
        assert is_empty_input_error(rec), (
            f"empty-input error is {rec!r}, not {EMPTY_INPUT_ERROR!r}"
        )
    for other in contrast_records:
        assert not is_empty_input_error(other), (
            f"a non-empty-input failure reports {EMPTY_INPUT_ERROR!r}: {other!r}"
        )


def require_stdout_utf8(result: RunResult) -> str:
    """Standard output uses UTF-8. A decode failure is a failed assertion."""
    try:
        decoded = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"standard output is not UTF-8: {exc}") from exc
    return decoded


# ---------------------------------------------------------------------------
# Invoke wrappers
# ---------------------------------------------------------------------------


def scan_stdin(
    text: str | bytes, extra_args: Sequence[str] = ()
) -> RunResult:
    with workspace() as ws:
        return ws.invoke(list(extra_args), stdin=text)


def scan_path(
    ws, relpath: str, extra_args: Sequence[str] = ()
) -> RunResult:
    dest = ws.resolve(relpath)
    return ws.invoke([*list(extra_args), str(dest)])


def unicode_len(text: str) -> int:
    return len(text)


# ---------------------------------------------------------------------------
# Usage / switches (Contract: literal spellings)
# ---------------------------------------------------------------------------


def fold_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def padding_of_length(n: int, unit: str = "bridge ") -> str:
    if n < 1:
        raise ValueError("n must be positive")
    text = (unit * (n // len(unit) + 1))[:n]
    if len(text) != n:
        raise HarnessError(f"could not build a pad of length {n}")
    return text


def usage_from_help(token: str = "--help") -> str:
    """Usage printed by a help switch (exit 0, stdout)."""
    result = invoke([token])
    assert result.returncode == 0, (
        f"{token} exited {result.returncode}; stderr={result.stderr_text[:300]!r}"
    )
    text = result.stdout_text
    require_usage_message(text)
    return text


def _usage_line_flags(line: str) -> list[str]:
    flags = re.findall(r"--[A-Za-z][\w-]*", line)
    return [f for f in flags if f.lower() not in {"--help"}]


def _strip_usage_flags(line: str) -> str:
    return re.sub(r"--[A-Za-z][\w-]*", " ", line)


def _is_usage_synopsis_line(line: str) -> bool:
    return line.strip().lower().startswith("usage")


_CONCEPT_FLAGS = {
    "cleanup": CLEANUP_FLAG,
    "clean": CLEANUP_FLAG,
    "scrub": CLEANUP_FLAG,
    "interval": INTERVAL_FLAG,
    "resample": INTERVAL_FLAG,
}


def switch_from_usage(usage: str, talks=None, concept: str = "") -> str:
    """The Contract's literal switch for *concept* (no discovery from usage)."""
    low = concept.lower()
    for word, flag in _CONCEPT_FLAGS.items():
        if word in low:
            return flag
    raise HarnessError(f"no stated switch for concept {concept!r}")


def interval_flag_from_usage(usage: str = "") -> str:
    return INTERVAL_FLAG


def usage_synopsis_line(usage: str) -> str:
    lines = usage.splitlines()
    assert lines, "usage message is empty"
    return lines[0].rstrip("\r")


def require_usage_message(text: str) -> None:
    """The usage message's first line is exactly the stated synopsis."""
    assert str(text).strip(), "usage message is empty"
    first = usage_synopsis_line(text)
    assert first == USAGE_SYNOPSIS, (
        f"usage first line is {first!r}, expected {USAGE_SYNOPSIS!r}"
    )


def usage_names_concepts(usage: str) -> None:
    require_usage_message(usage)


def usage_names_end_of_options_double_dash(usage: str) -> None:
    require_usage_message(usage)


def usage_names_single_file_operand(usage: str) -> None:
    require_usage_message(usage)


def _is_json_object_line(line: str) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except (ValueError, TypeError):
        return False


def multi_file_notice_lines(text: str, operand: str) -> list[str]:
    """Contract: the multi-file notice is a stderr line, not a JSON object,
    that contains the first operand exactly as given."""
    return [
        ln for ln in text.splitlines()
        if ln.strip() and operand in ln and not _is_json_object_line(ln.strip())
    ]


def stderr_states_one_file_at_a_time(text: str, scanned: str) -> None:
    """The stated multi-file notice line names the scanned (first) operand."""
    hits = multi_file_notice_lines(text, scanned)
    assert hits, f"error stream has no notice line naming {scanned!r}: {text!r}"



def band_named_for_score(score: int) -> str:
    """The unique L98 band whose range contains *score*."""
    if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
        raise HarnessError(f"score {score!r} is outside 0–100")
    matches = [
        name for name, (lo, hi) in BAND_RANGES.items() if lo <= score <= hi
    ]
    assert len(matches) == 1, (
        f"score {score} is not in exactly one of the five L98 band ranges: "
        f"{matches!r}"
    )
    return matches[0]


# ---------------------------------------------------------------------------
# Padding / twins
# ---------------------------------------------------------------------------


def neutral_words(n: int, token: str = "bridge") -> str:
    if n < 1:
        raise ValueError("n must be positive")
    return " ".join([token] * n)


def pad_human(n_words: int) -> str:
    """Varied factual sentences so length is not a memorized blob.

    Every run of five or more consecutive words holds a token tagged by
    its sentence index (letters only, so a letter-only word splitter sees
    the same tokens), so no span of several words recurs anywhere in the
    pad and it carries no degenerate repetition (71). Lengths stay uneven
    and do not zigzag sentence by sentence, so the pad is not a rhythm-class
    carrier.
    """
    templates = (
        "Tally{i} notes mason{i} measured pier{i}.",
        "Beam{i} still sits true beside mark{i}.",
        "On day{i} the mason at kiln{i} pointed chamber{i} with lime after flood{i} receded along wall{i} on the east side{i}.",
        "A clerk at desk{i} listed every stone from quay{i} beside lock{i} after storm{i} stripped moss from face{i} of the inner pier{i}.",
        "Oak post{i} holds the walkway.",
        "Barges at berth{i} waited below ridge{i} until lock{i} opened at dawn for the survey{i}.",
        "Lime coat{i} remains on the inner face{i} of chamber{i} near gate{i} where the gates meet sill{i} today.",
    )
    sentences: list[str] = []
    words: list[str] = []
    i = 1
    while len(words) < n_words:
        tag = "".join("abcdefghij"[int(d)] for d in str(i))
        sentence = templates[(i - 1) % len(templates)].format(i=tag)
        sentences.append(sentence)
        words.extend(re.findall(r"[\w'-]+", sentence))
        i += 1
    return " ".join(sentences)


def runtime_twin(kind: str) -> str:
    if kind == "factual":
        return SHORT_FACTUAL_TWIN
    if kind == "slop":
        return SHORT_SLOP_TWIN
    if kind == "placeholder":
        return (
            f"Please send the draft to {PLACEHOLDER_TWIN} before noon. "
            f"See {TRACKING_URL_TWIN} for the rest."
        )
    if kind == "cafe":
        return "The naïve résumé sat on the oak desk beside a brass lamp."
    raise HarnessError(f"unknown twin kind {kind!r}")


def zw_split(word: str, mark: str | None = None) -> str:
    """Split *word* with one in-word zero-width character. Do not pin the codepoint."""
    if len(word) < 2:
        raise ValueError("word too short to split")
    if mark is None:
        mark = "\u200b"
    mid = len(word) // 2
    return word[:mid] + mark + word[mid:]


def latin_homoglyph(word: str, cyrillic: str = "\u0430") -> str:
    """Replace one Latin letter with a lookalike that folds back to that letter."""
    fold = {
        "\u0430": "a",
        "\u043e": "o",
        "\u03bf": "o",
        "\u0435": "e",
        "\u0441": "c",
        "\u0455": "s",
        "\u0440": "p",
        "\u0445": "x",
        "\u0443": "y",
        "\u0456": "i",
        "\u04bb": "h",
    }
    target = fold.get(cyrillic, "a")
    for index, ch in enumerate(word):
        if ch.lower() == target:
            return word[:index] + cyrillic + word[index + 1 :]
    for index, ch in enumerate(word):
        if "a" <= ch.lower() <= "z" and ord(ch) < 128:
            return word[:index] + cyrillic + word[index + 1 :]
    return cyrillic + word[1:]


_LOOKALIKE_FOLD = {
    "\u0430": "a",
    "\u043e": "o",
    "\u03bf": "o",
    "\u0435": "e",
    "\u0441": "c",
    "\u0455": "s",
    "\u0440": "p",
    "\u0445": "x",
    "\u0443": "y",
    "\u0456": "i",
    "\u04bb": "h",
}


def fold_lookalikes(text: str) -> str:
    """*text* with every planted lookalike letter replaced by its Latin letter."""
    return "".join(_LOOKALIKE_FOLD.get(ch, ch) for ch in text)


# Contrast arms for the three L97 character-layer counts. Each pair is the
# same prose; only the second arm carries the marks being counted.
NBSP_PROBE = (
    "Two\u00a0words sit on the\u00a0page near the\u00a0lock by the\u00a0weir "
    "at\u00a0dawn."
)


def zero_width_arms() -> tuple[str, str]:
    return SHORT_FACTUAL, SHORT_FACTUAL[:40] + "\u200b" * 5 + SHORT_FACTUAL[40:]


def nonstandard_space_arms() -> tuple[str, str]:
    return NBSP_PROBE.replace("\u00a0", " "), NBSP_PROBE


def lookalike_arms() -> tuple[str, str]:
    mixed = (
        f"They {latin_homoglyph('showcase')} the "
        f"{latin_homoglyph('seamless', chr(0x043e))} "
        f"{latin_homoglyph('tapestry', chr(0x0435))} "
        f"{latin_homoglyph('pivotal', chr(0x0430))} "
        f"{latin_homoglyph('robust', chr(0x043e))} latch."
    )
    return fold_lookalikes(mixed), mixed


def bind_character_layer_slot(slot: str) -> None:
    """Bind one L97 character-layer count from its property-only contrast."""
    arms = {
        "invisible": (zero_width_arms, bind_invisible_count),
        "space": (nonstandard_space_arms, bind_nonstandard_space_count),
        "mixed": (lookalike_arms, bind_mixed_script_count),
    }
    if slot not in arms:
        raise HarnessError(f"unknown character-layer slot {slot!r}")
    build, bind = arms[slot]
    plain, marked = build()
    _pf, plain_m = require_success_report(
        scan_stdin(plain), input_chars=unicode_len(plain)
    )
    _mf, marked_m = require_success_report(
        scan_stdin(marked), input_chars=unicode_len(marked)
    )
    bind(plain_m, marked_m)


def rhythm_uniform_paragraphs(paragraphs: int = 8, words: int = 10) -> str:
    """Equal-length factual paragraphs (rhythm class: uniform paragraph length)."""
    if paragraphs < 2:
        raise ValueError("need at least two paragraphs")
    subjects = [
        "Iron beams",
        "Stone piers",
        "Oak planks",
        "Brick walls",
        "Clay tiles",
        "Lead joints",
        "Pine posts",
        "Slate slabs",
        "Lime coats",
        "Sand beds",
        "Ash rails",
        "Elm gates",
    ]
    # "Iron beams hold the old deck up still now." is 9 words; pad to *words*.
    base_tail = "hold the old deck up still now"
    extra = max(0, words - 9)
    pad = " " + " ".join(f"mark{j}" for j in range(extra)) if extra else ""
    parts = []
    for i in range(paragraphs):
        line = f"{subjects[i % len(subjects)]} {base_tail}{pad}.".strip()
        parts.append(line)
    return "\n\n".join(parts)


def rhythm_alternating_cadence(pairs: int = 6) -> str:
    """Short then long factual sentences (writing-advice: mechanical alternation)."""
    if pairs < 3:
        raise ValueError("need at least three short/long pairs")
    bits: list[str] = []
    for i in range(pairs):
        bits.append(f"Iron post{i} holds.")
        bits.append(
            f"The masonry along quay{i} still faces west after the spring flood "
            f"receded from the inner chamber wall beside lock{i}."
        )
    return " ".join(bits)


def rhythm_only_candidate_texts() -> tuple[str, ...]:
    """Documents that may exhibit L104 rhythm-only evidence.

    Sentence-length monotony, mechanical alternation, uniform paragraph
    length, and contraction absence are the named kinds. L104 does not
    give a constructable fire for 40, 41, 44, or 55, so these texts are
    not a must-fire table for even-length, equal-length, short-then-long,
    or contraction-absence pads. Length and paragraph count vary so a
    detector that uses a different rhythm trigger still counts. The
    caller keeps the cap when rhythm-class evidence is actually present
    and is the only score-moving evidence.
    """
    texts: list[str] = []
    for count, words in (
        (6, 7),
        (8, 7),
        (10, 8),
        (12, 9),
        (16, 6),
        (20, 11),
        (8, 12),
        (14, 5),
    ):
        texts.append(rhythm_monotony_document(sentences=count, words=words))
    for count, words in ((4, 10), (6, 8), (8, 12), (12, 9), (5, 15)):
        texts.append(rhythm_uniform_paragraphs(count, words=words))
    for count in (4, 6, 10, 8):
        texts.append(rhythm_alternating_cadence(count))
    texts.append(CONTRACTABLE_OPINION)
    texts.append(
        "Iron beams hold. Stone piers hold. Oak planks hold. Brick walls hold. "
        "Clay tiles hold. Lead joints hold. Pine posts hold. Slate slabs hold."
    )
    return tuple(texts)


def rhythm_monotony_document(sentences: int = 8, words: int = 7) -> str:
    """Even-length factual sentences (rhythm class: sentence-length monotony)."""
    subjects = [
        "Iron beams",
        "Stone piers",
        "Oak planks",
        "Brick walls",
        "Clay tiles",
        "Lead joints",
        "Pine posts",
        "Slate slabs",
        "Lime coats",
        "Sand beds",
    ]
    tail = "hold the old deck up."
    # "Iron beams hold the old deck up." → 7 words
    parts = []
    for i in range(sentences):
        subj = subjects[i % len(subjects)]
        extra = "" if words <= 7 else " still"
        line = f"{subj}{extra} {tail}".strip()
        parts.append(line)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Network observer
# ---------------------------------------------------------------------------


@contextmanager
def proxy_sink() -> Iterator[Any]:
    connections: list[float] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(32)
    sock.settimeout(0.2)
    port = sock.getsockname()[1]
    stop = threading.Event()

    def _accept() -> None:
        while not stop.is_set():
            try:
                client, _addr = sock.accept()
                connections.append(time.time())
                try:
                    client.close()
                except OSError:
                    pass
            except socket.timeout:
                continue
            except OSError:
                break

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()

    class Sink:
        url = f"http://127.0.0.1:{port}"
        hostport = f"127.0.0.1:{port}"

        @property
        def n_connections(self) -> int:
            return len(connections)

        def fire_positive_control(self) -> None:
            before = len(connections)
            probe = socket.create_connection(("127.0.0.1", port), timeout=2)
            probe.close()
            deadline = time.time() + 2.0
            while time.time() < deadline and len(connections) <= before:
                time.sleep(0.05)
            if len(connections) <= before:
                raise HarnessError(
                    "proxy sink observed no connect from the positive control"
                )

    try:
        yield Sink()
    finally:
        stop.set()
        try:
            sock.close()
        except OSError:
            pass
        thread.join(timeout=1.0)
