"""Pipeline-owned sealed test helpers.

This file is the complete module. Import what you need (`from _helpers import ...`). Add a new helper here, with the imports and constants it closes over. Do not paste a sealed body into a feature file. Do not change a sealed name unless you own it and that feature's PRD was amended.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from numbers import Real
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from _harness import (
    CallResult,
    HarnessError,
    InvokeResult,
    RunResult,
    call,
    replace_list,
)

# Resource name of the English sentence-boundary model (Interface Contract table).
_ENGLISH_SENTENCE_RESOURCE = "tokenizers/punkt_tab/english/"


def _stderr_snippet(result: Any) -> str:
    """Decode stderr for a failure message; never invent a stand-in."""
    getter = getattr(result, "stderr_text", None)
    if getter is None:
        raw = getattr(result, "stderr", None)
        if raw is None:
            return ""
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HarnessError(f"stderr is not valid UTF-8: {exc}") from exc
    try:
        return getter
    except HarnessError:
        raise


def _cli_status(result: Any) -> int:
    """Return a process-style status from an invoke or subprocess result."""
    if isinstance(result, InvokeResult):
        return result.exit_code
    if isinstance(result, RunResult):
        return result.returncode
    code = getattr(result, "exit_code", None)
    if isinstance(code, int):
        return code
    code = getattr(result, "returncode", None)
    if isinstance(code, int):
        return code
    raise HarnessError(
        f"cannot read a process status from result of type {type(result)!r}"
    )


def require_token_list(result: CallResult) -> list[str]:
    """Return the successful token list, or raise.

    A product exception, a non-list, or a list that is not all strings is
    a hard failure. An empty list is a successful empty result, never a
    stand-in for "the call could not be performed".
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_token_list expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "tokenizer did not return a token list: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AssertionError(
            "tokenizer did not return a list of strings: "
            f"{type(value).__name__} {value!r}"
        )
    return value


def tokens_of(fn: Callable[..., Any], text: str, **kwargs: Any) -> list[str]:
    """Call a public tokenizer entry and return its token list."""
    return require_token_list(call(fn, text, **kwargs))


def require_unsuccessful(result: CallResult) -> BaseException:
    """Library path: the call did not yield a successful token list.

    A successful empty list is success, not a refusal. Any other
    unclassifiable return (no exception, not a token list) raises.
    Does not map an exception onto ``[]``.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_unsuccessful expects a CallResult; got {type(result)!r}"
        )
    if result.exception is None:
        value = result.value
        if value == []:
            raise AssertionError(
                "call succeeded with an empty token list; that is a "
                "successful empty result, not a missing-model refusal"
            )
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            raise AssertionError(
                f"call succeeded with a token list {value!r}; "
                "a missing-model path must not succeed"
            )
        raise AssertionError(
            f"call returned {type(value).__name__} {value!r} without "
            "raising; cannot classify as a token-list refusal"
        )
    stderr = _stderr_snippet(result)
    print(
        f"unsuccessful {type(result.exception).__name__}: {result.exception}; "
        f"stderr={stderr!r}",
        flush=True,
    )
    return result.exception


def cli_output_lines(result: Any) -> list[str]:
    """Decode stdout as UTF-8 and split into lines.

    Does not interpret the process status. Decode failure raises.
    """
    getter = getattr(result, "stdout_text", None)
    if getter is None:
        raise HarnessError(
            f"cli_output_lines cannot read stdout from {type(result)!r}"
        )
    text = getter
    return text.splitlines()


def require_cli_non_success(
    result: Any,
    *,
    success_line: str | None = None,
) -> None:
    """Command-line path: process status is not success.

    Any non-zero status counts. Exit 0 — including empty or garbage
    output — is not a missing-model refusal. When *success_line* is
    given, that exact successful write must also be absent.
    Does not pin which non-zero number, stderr wording, or exception type.
    """
    status = _cli_status(result)
    lines = cli_output_lines(result)
    print(f"cli status={status} lines={lines!r}", flush=True)
    if status == 0:
        raise AssertionError(
            "command-line status was success (0); empty or garbage "
            f"output is not a missing-model refusal. lines={lines!r}"
        )
    if success_line is not None and success_line in lines:
        raise AssertionError(
            "command-line status was non-zero but the successful token "
            f"line was written: {success_line!r}; lines={lines!r}"
        )


def assert_spans_recover(
    text: str,
    tokens: Sequence[str],
    spans: Any,
) -> None:
    """Each span is an offset pair; slicing recovers the token; ordered; disjoint.

    A failure to read spans raises. Integer pairs themselves are not
    pinned as golden values.
    """
    if spans is None:
        raise AssertionError("span extraction returned None")
    try:
        pairs = list(spans)
    except TypeError as exc:
        raise AssertionError(f"spans are not iterable: {exc}") from exc
    if len(pairs) != len(tokens):
        raise AssertionError(
            f"span count {len(pairs)} != token count {len(tokens)}: "
            f"spans={pairs!r} tokens={list(tokens)!r}"
        )
    prev_end = 0
    for index, (token, span) in enumerate(zip(tokens, pairs)):
        if not (isinstance(span, (tuple, list)) and len(span) == 2):
            raise AssertionError(f"span {index} is not a pair: {span!r}")
        start, end = span
        if not isinstance(start, int) or not isinstance(end, int):
            raise AssertionError(f"span {index} offsets are not integers: {span!r}")
        recovered = text[start:end]
        if recovered != token:
            raise AssertionError(
                f"slice [{start}:{end}] is {recovered!r}, expected token {token!r}"
            )
        if index > 0 and start < prev_end:
            raise AssertionError(
                f"spans are not left-to-right / non-overlapping at {index}: "
                f"{pairs[index - 1]!r} then {span!r}"
            )
        prev_end = end










# Finder resource for a language stopwords list (directory form, not a zip name).
_STOPWORDS_CORPUS_RESOURCE = "corpora/stopwords"


def require_stem(result: CallResult) -> str:
    """Return the successful stem string, or raise.

    A product exception or a non-str value is a hard failure. An empty
    string is a successful stem, never a stand-in for "the call could
    not be performed". Never maps a failure onto the original word.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_stem expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "stemmer did not return a stem string: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if not isinstance(value, str):
        raise AssertionError(
            f"stemmer did not return a string: {type(value).__name__} {value!r}"
        )
    return value


def stem_of(fn: Callable[..., Any], word: str, **kwargs: Any) -> str:
    """Call a public stem entry and return its stem string."""
    return require_stem(call(fn, word, **kwargs))


def require_constructed(result: CallResult) -> Any:
    """Return a usable stemmer instance, or raise.

    Usable means the constructor yielded an object with a callable
    ``stem`` that returns a ``str`` for one probe token. Does not return
    ``None`` to mean "construction failed".
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_constructed expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "constructor did not yield a usable stemmer: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    inst = result.value
    stem_fn = getattr(inst, "stem", None)
    if not callable(stem_fn):
        raise AssertionError(
            "constructed value has no callable stem: "
            f"{type(inst).__name__} {inst!r}"
        )
    probe = call(stem_fn, "x")
    require_stem(probe)
    return inst


def require_not_constructed(result: CallResult) -> CallResult:
    """Construction path: no usable stemmer was yielded.

    A usable instance (callable ``stem`` that returns a ``str``) is
    construction success and must raise. Does not pin an exception type.
    An unclassifiable outcome raises.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_not_constructed expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"construct unsuccessful {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    inst = result.value
    stem_fn = getattr(inst, "stem", None)
    if callable(stem_fn):
        probe = call(stem_fn, "x")
        if probe.exception is None and isinstance(probe.value, str):
            raise AssertionError(
                "constructor yielded a usable stemmer "
                f"{type(inst).__name__} that stemmed to {probe.value!r}"
            )
        print(
            "constructed value is not a usable stemmer: "
            f"stem exception={probe.exception!r} value={probe.value!r}",
            flush=True,
        )
        return result
    print(
        f"constructor returned non-stemmer {type(inst).__name__} {inst!r}",
        flush=True,
    )
    return result


def require_no_lemma(result: CallResult) -> Any:
    """WordNet lemmatize path: no lemma string was yielded.

    A returned ``str`` (including the original word unchanged) is
    success and must raise. Unsuccess is the absence of a lemma string
    (an exception or a non-str value). Does not require an exception
    and does not pin an exception type. Unclassifiable outcomes raise.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_no_lemma expects a CallResult; got {type(result)!r}"
        )
    if result.exception is None and isinstance(result.value, str):
        raise AssertionError(
            "lemmatize succeeded with a lemma string "
            f"{result.value!r}; a missing-WordNet path must not succeed"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"lemmatize unsuccessful {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result.exception
    print(
        f"lemmatize returned non-string {type(result.value).__name__} "
        f"{result.value!r}",
        flush=True,
    )
    return result.value


def unsuccessful_observation(result: CallResult) -> str:
    """Collect observable text from an unsuccessful CallResult.

    Joins whatever actually appeared: exception text and arguments,
    a non-success return value, stderr, and stdout. Does not treat
    ``str(exc)`` as the only channel. An empty observation raises —
    that is not "the request was identified".
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"unsuccessful_observation expects a CallResult; got {type(result)!r}"
        )
    parts: list[str] = []
    if result.exception is not None:
        parts.append(type(result.exception).__name__)
        parts.append(str(result.exception))
        args = getattr(result.exception, "args", ())
        try:
            for arg in args:
                parts.append(str(arg))
        except TypeError:
            parts.append(str(args))
    if result.value is not None:
        parts.append(str(result.value))
    stderr = _stderr_snippet(result)
    if stderr:
        parts.append(stderr)
    try:
        stdout = result.stdout_text
    except HarnessError:
        raise
    if stdout:
        parts.append(stdout)
    text = "\n".join(part for part in parts if part)
    if not text.strip():
        raise AssertionError(
            "unsuccessful call produced no observable text"
        )
    return text












def write_stopwords_list(ws: Any, language: str, words: Sequence[str]) -> Path:
    """Write a language wordlist into *ws.data* at the packaged-list path.

    Installs only that language's list. Empty *words* raises. Write
    failure raises. Never downloads. Never skips.
    """
    items = list(words)
    if not items:
        raise HarnessError(f"cannot install an empty {language!r} stopwords list")
    if not all(isinstance(item, str) and item for item in items):
        raise HarnessError(
            f"{language!r} stopwords list is not all non-empty strings: {items!r}"
        )
    dest = Path(ws.data) / _STOPWORDS_CORPUS_RESOURCE / language
    payload = "\n".join(items) + "\n"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise HarnessError(
            f"failed to write {language!r} stopwords list into the workspace: {exc}"
        ) from exc
    try:
        if dest.stat().st_size == 0:
            raise HarnessError(
                f"written {language!r} stopwords list is empty: {dest}"
            )
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(
            f"written {language!r} stopwords list is unreadable: {exc}"
        ) from exc
    print(
        f"wrote {language!r} stopwords list at {dest} ({len(items)} words)",
        flush=True,
    )
    return dest




# Resource names of the recommended averaged perceptron tagger and the
# packaged English universal tagset tables. Tests never download; they copy what
# the environment's resource directory holds. These are directory
# resource names, not a checkout-only zip filename.
_UNIVERSAL_TAGSET_RESOURCE = "taggers/universal_tagset/"


def _perceptron_resource(language: str) -> str:
    return f"taggers/averaged_perceptron_tagger_{language}/"


def _is_nonstring_sequence(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray)):
        return False
    try:
        iter(value)
    except TypeError:
        return False
    return True


def _pairing_components(pairing: Any) -> tuple[Any, Any]:
    """Read token and tag components from one pairing. Failure raises."""
    if pairing is None:
        raise AssertionError("tagged pairing is None")
    if isinstance(pairing, (str, bytes, bytearray)):
        raise AssertionError(
            f"tagged pairing is a string, not a token/tag pair: {pairing!r}"
        )
    try:
        parts = list(pairing)
    except TypeError as exc:
        raise AssertionError(
            f"tagged pairing is not a sequence: {type(pairing).__name__} {pairing!r}"
        ) from exc
    if len(parts) < 2:
        raise AssertionError(
            f"tagged pairing does not have token and tag components: {pairing!r}"
        )
    return parts[0], parts[1]


def _pairing_list_from_value(value: Any) -> list[Any] | None:
    """Return pairings if *value* is a sequence of pairings; otherwise None.

    A string is not a pairing sequence. An empty sequence is ``[]``.
    A sequence whose items are not pairings is not a pairing list (None).
    Does not raise for a classifiable non-pairing value.
    """
    if not _is_nonstring_sequence(value):
        return None
    try:
        items = list(value)
    except TypeError:
        return None
    if not items:
        return []
    pairings: list[Any] = []
    for item in items:
        try:
            _pairing_components(item)
        except AssertionError:
            return None
        pairings.append(item)
    return pairings


def _tagging_value_is_unclassifiable(value: Any) -> bool:
    """True when a non-exception return cannot be a pairing list or a refusal."""
    if isinstance(value, (str, bytes, bytearray)):
        return False
    if _is_nonstring_sequence(value):
        return False
    return True


def tag_value(pairing: Any) -> str:
    """Read the tag component. Read failure raises; no sentinel."""
    _token, tag = _pairing_components(pairing)
    if not isinstance(tag, str):
        raise AssertionError(
            f"tag is not a string: {type(tag).__name__} {tag!r}"
        )
    return tag


def assert_tag_absent(pairing: Any) -> None:
    """This position has no tag string. Any ``str`` tag is an invented tag."""
    _token, tag = _pairing_components(pairing)
    if isinstance(tag, str):
        raise AssertionError(
            f"expected no tag string; pairing invented {tag!r}"
        )
    print(f"tag absent on {_token!r}: {tag!r}", flush=True)


def assert_tag_equals(pairing: Any, expected: str) -> None:
    """Tag is the PRD-named tag string."""
    got = tag_value(pairing)
    token, _tag = _pairing_components(pairing)
    print(f"tag of {token!r}={got!r} expected={expected!r}", flush=True)
    if got != expected:
        raise AssertionError(
            f"tag of {token!r} is {got!r}, expected {expected!r}"
        )


def assert_same_tag(left: Any, right: Any) -> None:
    """Two pairings carry the same tag string. Read failure raises."""
    left_tag = tag_value(left)
    right_tag = tag_value(right)
    left_tok, _ = _pairing_components(left)
    right_tok, _ = _pairing_components(right)
    print(
        f"same-tag {left_tok!r}={left_tag!r} {right_tok!r}={right_tag!r}",
        flush=True,
    )
    if left_tag != right_tag:
        raise AssertionError(
            f"tags differ: {left_tok!r}={left_tag!r} {right_tok!r}={right_tag!r}"
        )


def assert_distinct_tags(left: Any, right: Any) -> None:
    """Two pairings carry different tag strings. Read failure raises."""
    left_tag = tag_value(left)
    right_tag = tag_value(right)
    left_tok, _ = _pairing_components(left)
    right_tok, _ = _pairing_components(right)
    print(
        f"distinct-tag {left_tok!r}={left_tag!r} {right_tok!r}={right_tag!r}",
        flush=True,
    )
    if left_tag == right_tag:
        raise AssertionError(
            f"tags are not distinct: {left_tok!r} and {right_tok!r} both {left_tag!r}"
        )


def require_tagged_tokens(result: CallResult, tokens: Sequence[str]) -> list[Any]:
    """Return pairings aligned with *tokens*, or raise.

    An exception, a non-sequence, a length mismatch, or a token that does
    not match the input is a hard failure. Never maps a failure onto ``[]``.
    Empty input with an empty pairing list is success.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_tagged_tokens expects a CallResult; got {type(result)!r}"
        )
    expected = list(tokens)
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "tagger did not return tagged tokens: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    pairings = _pairing_list_from_value(result.value)
    if pairings is None:
        raise AssertionError(
            "tagger did not return a sequence of tagged pairings: "
            f"{type(result.value).__name__} {result.value!r}"
        )
    if len(pairings) != len(expected):
        raise AssertionError(
            f"tagged count {len(pairings)} != token count {len(expected)}: "
            f"tagged={pairings!r} tokens={expected!r}"
        )
    for index, (token, pairing) in enumerate(zip(expected, pairings)):
        got_token, _tag = _pairing_components(pairing)
        if got_token != token:
            raise AssertionError(
                f"tagged token {index} is {got_token!r}, expected {token!r}"
            )
    print(f"tagged {len(pairings)} tokens aligned with input", flush=True)
    return pairings


def tagged_of(fn: Callable[..., Any], tokens: Sequence[str], **kwargs: Any) -> list[Any]:
    """Call a public tag / recommended entry and return aligned pairings."""
    return require_tagged_tokens(call(fn, list(tokens), **kwargs), tokens)


def require_tagging_unsuccessful(
    result: CallResult, tokens: Sequence[str]
) -> CallResult:
    """Token-list tagging call: did not yield an aligned tagged list.

    An aligned tagged list on nonempty input must raise. Empty input with
    ``[]`` is success, not a refusal. Does not pin an exception type.
    An unclassifiable outcome raises.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_tagging_unsuccessful expects a CallResult; got {type(result)!r}"
        )
    expected = list(tokens)
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"tagging unsuccessful {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _tagging_value_is_unclassifiable(value):
        raise AssertionError(
            f"call returned {type(value).__name__} {value!r} without "
            "raising; cannot classify as a tagging refusal"
        )
    pairings = _pairing_list_from_value(value)
    if pairings is not None and len(pairings) == len(expected):
        aligned = True
        for token, pairing in zip(expected, pairings):
            got_token, _tag = _pairing_components(pairing)
            if got_token != token:
                aligned = False
                break
        if aligned:
            if expected == []:
                raise AssertionError(
                    "call succeeded with an empty tagged list; that is a "
                    "successful empty result, not a tagging refusal"
                )
            raise AssertionError(
                f"call succeeded with aligned tagged tokens {pairings!r}; "
                "a missing-resource or unsupported-language path must not succeed"
            )
    print(
        f"tagging not aligned with {expected!r}: "
        f"{type(value).__name__} {value!r}",
        flush=True,
    )
    return result


def require_no_tagged_sequence(result: CallResult) -> CallResult:
    """Raw-string arm: did not yield a nonempty tagged-pairing sequence.

    A nonempty pairing sequence must raise (it was tagged). ``[]``, a
    product exception, a string, or a non-pairing sequence is not tagged.
    An unclassifiable scalar raises. Does not pin an exception type.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_no_tagged_sequence expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"raw-string tagging unsuccessful {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if isinstance(value, (str, bytes, bytearray)):
        print(
            f"raw-string path returned a string, not a tagged sequence: {value!r}",
            flush=True,
        )
        return result
    if _tagging_value_is_unclassifiable(value):
        raise AssertionError(
            f"call returned {type(value).__name__} {value!r} without "
            "raising; cannot classify as a raw-string refusal"
        )
    pairings = _pairing_list_from_value(value)
    if pairings is not None and len(pairings) >= 1:
        raise AssertionError(
            "raw-string path produced a nonempty tagged-pairing sequence "
            f"{pairings!r}; that is a successful tagging"
        )
    print(
        f"raw-string path did not produce a tagged sequence: "
        f"{type(value).__name__} {value!r}",
        flush=True,
    )
    return result


def english_universal_mapping_absent(
    result: CallResult, tokens: Sequence[str]
) -> list[Any] | CallResult:
    """English recommended entry with universal requested: mapping did not happen.

    If an aligned tagged list is returned, John and idea must not share a
    tag (the named collapse did not appear), and that list is returned.
    Returning unmapped tags is mapping-absent, not a helper failure. If no
    aligned tagged list is produced, mapping did not happen; that is
    allowed. Unclassifiable garbage raises. Pairing-read failure raises.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"english_universal_mapping_absent expects a CallResult; "
            f"got {type(result)!r}"
        )
    expected = list(tokens)
    try:
        john_at = expected.index("John")
        idea_at = expected.index("idea")
    except ValueError as exc:
        raise HarnessError(
            "english_universal_mapping_absent requires John and idea in tokens"
        ) from exc
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"english universal mapping did not yield tagged tokens: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _tagging_value_is_unclassifiable(value):
        raise AssertionError(
            f"english universal call returned {type(value).__name__} "
            f"{value!r} without raising; cannot classify mapping absence"
        )
    pairings = _pairing_list_from_value(value)
    aligned = False
    if pairings is not None and len(pairings) == len(expected):
        aligned = True
        for token, pairing in zip(expected, pairings):
            got_token, _tag = _pairing_components(pairing)
            if got_token != token:
                aligned = False
                break
    if not aligned:
        print(
            "english universal mapping did not yield an aligned tagged list: "
            f"{type(value).__name__} {value!r}",
            flush=True,
        )
        return result
    john_tag = tag_value(pairings[john_at])
    idea_tag = tag_value(pairings[idea_at])
    print(
        f"english universal without tables: John={john_tag!r} idea={idea_tag!r}",
        flush=True,
    )
    if john_tag == idea_tag:
        raise AssertionError(
            "John and idea share a tag "
            f"{john_tag!r}; English universal collapse must not appear "
            "without the packaged tables"
        )
    return pairings
















# Resource name of the packaged named-entity chunker (directory form, not a
# checkout-only zip filename). Tests never download; they copy whatever the
# environment's resource directory holds.
_NE_CHUNKER_RESOURCE = "chunkers/maxent_ne_chunker_tab/english_ace_multiclass/"

# The named-entity path's feature detector reads the packaged English wordlist.
_ENGLISH_WORDS_RESOURCE = "corpora/words"


def pairing_token(pairing: Any) -> Any:
    """Read the token component. Read failure raises; no sentinel."""
    token, _tag = _pairing_components(pairing)
    return token


def _pairing_key(pairing: Any) -> tuple[Any, str]:
    return pairing_token(pairing), tag_value(pairing)


def _has_label_hook(node: Any) -> bool:
    getter = getattr(node, "label", None)
    return callable(getter) or isinstance(getter, str)


def _read_label(node: Any) -> str:
    getter = getattr(node, "label", None)
    if callable(getter):
        try:
            label = getter()
        except Exception as exc:
            raise AssertionError(
                f"reading node label failed: {type(exc).__name__}: {exc}"
            ) from exc
    elif isinstance(getter, str):
        label = getter
    else:
        raise AssertionError(
            f"node has no readable label: {type(node).__name__} {node!r}"
        )
    if not isinstance(label, str):
        raise AssertionError(
            f"node label is not a string: {type(label).__name__} {label!r}"
        )
    return label


def _classify_node(node: Any) -> str:
    """Return ``'chunk'`` or ``'leaf'``. Unclassifiable raises."""
    if _has_label_hook(node):
        _read_label(node)
        if not _is_nonstring_sequence(node):
            raise AssertionError(
                f"labelled node is not traversable: {type(node).__name__} {node!r}"
            )
        return "chunk"
    try:
        _pairing_components(node)
    except AssertionError as exc:
        raise AssertionError(
            "node is neither a tagged pairing nor a labelled chunk: "
            f"{type(node).__name__} {node!r}"
        ) from exc
    return "leaf"


def node_label(node: Any) -> str:
    """Read an internal node's label string. Read failure raises."""
    return _read_label(node)


def is_tagged_leaf(node: Any) -> bool:
    """True when *node* is a tagged pairing. Unclassifiable raises."""
    return _classify_node(node) == "leaf"


def is_chunk_node(node: Any) -> bool:
    """True when *node* is a labelled internal node. Unclassifiable raises."""
    return _classify_node(node) == "chunk"


def chunk_children(tree: Any) -> list[Any]:
    """Root's direct children. Read failure raises; no sentinel."""
    if not _is_nonstring_sequence(tree):
        raise AssertionError(
            f"chunk node is not traversable: {type(tree).__name__} {tree!r}"
        )
    try:
        return list(tree)
    except TypeError as exc:
        raise AssertionError(
            f"chunk children are not traversable: {type(tree).__name__} {tree!r}"
        ) from exc


def chunk_leaves(tree: Any) -> list[Any]:
    """In-order tagged-pairing leaves. Read failure raises; no sentinel."""
    leaves: list[Any] = []

    def walk(node: Any) -> None:
        kind = _classify_node(node)
        if kind == "leaf":
            leaves.append(node)
            return
        for child in chunk_children(node):
            walk(child)

    walk(tree)
    return leaves


def _internal_chunk_nodes(tree: Any) -> list[Any]:
    """Non-root internal chunk nodes. Walk failure raises."""
    nodes: list[Any] = []

    def walk(node: Any, is_root: bool) -> None:
        kind = _classify_node(node)
        if kind == "leaf":
            return
        if not is_root:
            nodes.append(node)
        for child in chunk_children(node):
            walk(child, False)

    walk(tree, True)
    return nodes


def require_chunk_structure(result: CallResult) -> Any:
    """Return a chunk structure, or raise.

    A product exception, a missing root label, or children that cannot
    be traversed is a hard failure. Never maps a failure onto an empty
    tree. An empty child list is success only as a rooted structure.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_chunk_structure expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "chunker did not return a chunk structure: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    kind = _classify_node(value)
    if kind != "chunk":
        raise AssertionError(
            "chunker did not return a labelled chunk structure: "
            f"{type(value).__name__} {value!r}"
        )
    label = node_label(value)
    children = chunk_children(value)
    print(
        f"chunk structure root={label!r} n_children={len(children)}",
        flush=True,
    )
    return value


def chunked_of(
    fn: Callable[..., Any],
    grammar: str,
    tagged: Sequence[Any],
    **kwargs: Any,
) -> Any:
    """Construct a chunk parser from grammar text and apply it to *tagged*."""
    constructed = call(fn, grammar, **kwargs)
    if constructed.exception is not None:
        stderr = _stderr_snippet(constructed)
        raise AssertionError(
            "chunk-grammar constructor failed: "
            f"{type(constructed.exception).__name__}: {constructed.exception}; "
            f"stderr={stderr!r}"
        )
    inst = constructed.value
    parse_fn = getattr(inst, "parse", None)
    if not callable(parse_fn):
        raise AssertionError(
            "constructed value has no callable parse: "
            f"{type(inst).__name__} {inst!r}"
        )
    applied = call(parse_fn, list(tagged))
    return require_chunk_structure(applied)


def assert_leaves_equal(tree: Any, tagged: Sequence[Any]) -> None:
    """Leaves' (token, tag) sequence equals *tagged*. Read failure raises."""
    leaves = chunk_leaves(tree)
    expected = list(tagged)
    if len(leaves) != len(expected):
        raise AssertionError(
            f"leaf count {len(leaves)} != input count {len(expected)}: "
            f"leaves={leaves!r} input={expected!r}"
        )
    for index, (leaf, pair) in enumerate(zip(leaves, expected)):
        got = _pairing_key(leaf)
        want = _pairing_key(pair)
        if got != want:
            raise AssertionError(
                f"leaf {index} is {got!r}, expected {want!r}"
            )
    print(f"leaves equal input ({len(leaves)} pairings)", flush=True)


def assert_chunk_covers(tree: Any, tagged_span: Sequence[Any], label: str) -> None:
    """Some internal node labelled *label* has exactly *tagged_span* as leaves."""
    expected = [_pairing_key(p) for p in tagged_span]
    for node in _internal_chunk_nodes(tree):
        if node_label(node) != label:
            continue
        got = [_pairing_key(p) for p in chunk_leaves(node)]
        if got == expected:
            print(
                f"chunk {label!r} covers {expected!r}",
                flush=True,
            )
            return
    raise AssertionError(
        f"no internal node labelled {label!r} covers {expected!r}"
    )


def assert_direct_leaf(tree: Any, pairing: Any) -> None:
    """A direct child of the root is this tagged leaf, not inside a chunk."""
    want = _pairing_key(pairing)
    for child in chunk_children(tree):
        if is_tagged_leaf(child) and _pairing_key(child) == want:
            print(f"direct leaf {want!r}", flush=True)
            return
    raise AssertionError(
        f"{want!r} is not a direct tagged leaf of the root "
        f"(children={chunk_children(tree)!r})"
    )


def containing_chunks(tree: Any, token: Any) -> list[Any]:
    """Non-root internal nodes whose leaves include *token*. Walk failure raises."""
    found: list[Any] = []
    for node in _internal_chunk_nodes(tree):
        leaves = chunk_leaves(node)
        if any(pairing_token(leaf) == token for leaf in leaves):
            found.append(node)
    return found


def require_chunking_unsuccessful(result: CallResult) -> CallResult:
    """Did not yield a chunk structure. An empty tree is success and must raise."""
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_chunking_unsuccessful expects a CallResult; "
            f"got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"chunking unsuccessful {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if value is None:
        raise AssertionError(
            "call returned None without raising; cannot classify as a "
            "chunking refusal"
        )
    if _has_label_hook(value):
        kind = _classify_node(value)
        if kind == "chunk":
            raise AssertionError(
                "call succeeded with a chunk structure "
                f"(root={node_label(value)!r}, n_children="
                f"{len(chunk_children(value))}); a missing-resource path "
                "must not succeed, including as an empty tree"
            )
    if _is_nonstring_sequence(value) or isinstance(value, (str, bytes, bytearray)):
        print(
            f"chunking not a structure: {type(value).__name__} {value!r}",
            flush=True,
        )
        return result
    raise AssertionError(
        f"call returned {type(value).__name__} {value!r} without raising; "
        "cannot classify as a chunking refusal"
    )


def require_grammar_refused(result: CallResult) -> CallResult:
    """Constructor path: no parser that yields a chunk structure on tagged input."""
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_grammar_refused expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"grammar refused {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    inst = result.value
    parse_fn = getattr(inst, "parse", None)
    if not callable(parse_fn):
        print(
            f"constructed value is not a parser: {type(inst).__name__} {inst!r}",
            flush=True,
        )
        return result
    probe = [("x", "NN")]
    applied = call(parse_fn, probe)
    if applied.exception is None and _has_label_hook(applied.value):
        kind = _classify_node(applied.value)
        if kind == "chunk":
            raise AssertionError(
                "constructor yielded a parser that returned a chunk structure "
                f"{applied.value!r} for {probe!r}"
            )
    print(
        f"constructed value did not parse {probe!r} into a chunk structure: "
        f"exc={applied.exception!r} value={applied.value!r}",
        flush=True,
    )
    return result












def _production_rhs(prod: Any) -> Sequence[Any]:
    """Public RHS of one production. Read failure raises."""
    rhs_fn = getattr(prod, "rhs", None)
    if not callable(rhs_fn):
        raise AssertionError(
            f"production has no callable rhs: {type(prod).__name__} {prod!r}"
        )
    try:
        rhs = rhs_fn()
    except Exception as exc:
        raise AssertionError(
            f"reading production rhs failed: {type(exc).__name__}: {exc}"
        ) from exc
    if isinstance(rhs, (str, bytes, bytearray)):
        raise AssertionError(
            f"production rhs is a string, not a sequence: {rhs!r}"
        )
    try:
        return list(rhs)
    except TypeError as exc:
        raise AssertionError(
            f"production rhs is not iterable: {type(rhs).__name__} {rhs!r}"
        ) from exc


def _looks_like_constituent_tree(value: Any) -> bool:
    """True when *value* is a labelled, traversable constituent node."""
    if isinstance(value, (str, bytes, bytearray)):
        return False
    if not _has_label_hook(value):
        return False
    return _is_nonstring_sequence(value)


def _as_constituent_tree(value: Any) -> Any:
    """Return *value* as a constituent tree, or raise."""
    if not _looks_like_constituent_tree(value):
        raise AssertionError(
            "value is not a labelled constituent tree: "
            f"{type(value).__name__} {value!r}"
        )
    node_label(value)
    constituent_children(value)
    return value


def _constituent_kind(node: Any) -> str:
    """Return ``'internal'`` or ``'leaf'``. Unclassifiable raises."""
    if isinstance(node, str):
        return "leaf"
    if isinstance(node, (bytes, bytearray)):
        raise AssertionError(
            f"constituent node is bytes, not a token string: {node!r}"
        )
    if _looks_like_constituent_tree(node):
        return "internal"
    raise AssertionError(
        "node is neither a token-string leaf nor a labelled constituent: "
        f"{type(node).__name__} {node!r}"
    )


def require_grammar(result: CallResult) -> Any:
    """Return a grammar object, or raise.

    A product exception, or a value whose start symbol or production
    list cannot be read, is a hard failure. Never maps a failure onto
    ``[]`` productions.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_grammar expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "grammar reader did not yield a grammar: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    grammar = result.value
    grammar_start_symbol(grammar)
    grammar_productions(grammar)
    print("grammar reader yielded a grammar with readable start and productions", flush=True)
    return grammar


def grammar_start_symbol(grammar: Any) -> str:
    """Start-symbol string. Read failure raises."""
    start_fn = getattr(grammar, "start", None)
    if not callable(start_fn):
        raise AssertionError(
            f"grammar has no callable start: {type(grammar).__name__} {grammar!r}"
        )
    try:
        start = start_fn()
    except Exception as exc:
        raise AssertionError(
            f"reading grammar start failed: {type(exc).__name__}: {exc}"
        ) from exc
    if isinstance(start, str):
        if not start:
            raise AssertionError("grammar start symbol is an empty string")
        print(f"grammar start={start!r}", flush=True)
        return start
    symbol_fn = getattr(start, "symbol", None)
    if callable(symbol_fn):
        try:
            symbol = symbol_fn()
        except Exception as exc:
            raise AssertionError(
                f"reading start.symbol failed: {type(exc).__name__}: {exc}"
            ) from exc
        if isinstance(symbol, str) and symbol:
            print(f"grammar start={symbol!r}", flush=True)
            return symbol
        raise AssertionError(
            f"start.symbol() is not a non-empty string: {symbol!r}"
        )
    text = str(start)
    if not text:
        raise AssertionError(
            f"grammar start has no string form: {type(start).__name__} {start!r}"
        )
    print(f"grammar start={text!r}", flush=True)
    return text


def grammar_productions(grammar: Any) -> list[Any]:
    """Production sequence. Read failure raises.

    An empty list is returned only when the grammar actually yielded one.
    """
    prod_fn = getattr(grammar, "productions", None)
    if not callable(prod_fn):
        raise AssertionError(
            "grammar has no callable productions: "
            f"{type(grammar).__name__} {grammar!r}"
        )
    try:
        prods = prod_fn()
    except Exception as exc:
        raise AssertionError(
            f"reading grammar productions failed: {type(exc).__name__}: {exc}"
        ) from exc
    if isinstance(prods, (str, bytes, bytearray)):
        raise AssertionError(
            f"grammar productions are a string, not a sequence: {prods!r}"
        )
    try:
        items = list(prods)
    except TypeError as exc:
        raise AssertionError(
            "grammar productions are not iterable: "
            f"{type(prods).__name__} {prods!r}"
        ) from exc
    print(f"grammar production count={len(items)}", flush=True)
    return items


def grammar_terminals(grammar: Any) -> set[str]:
    """Terminal strings collected from public production right-hand sides.

    Does not read a private lexicon index. Read failure raises.
    """
    terminals: set[str] = set()
    for prod in grammar_productions(grammar):
        for item in _production_rhs(prod):
            if isinstance(item, str):
                terminals.add(item)
    print(f"grammar terminals={sorted(terminals)!r}", flush=True)
    return terminals


def parsed_with(parser_cls: Callable[..., Any], grammar: Any, tokens: Sequence[str]) -> list[Any]:
    """Construct a parser from *grammar* and return its parse-tree list."""
    constructed = call(parser_cls, grammar)
    if constructed.exception is not None:
        stderr = _stderr_snippet(constructed)
        raise AssertionError(
            "parser constructor failed: "
            f"{type(constructed.exception).__name__}: {constructed.exception}; "
            f"stderr={stderr!r}"
        )
    inst = constructed.value
    parse_fn = getattr(inst, "parse", None)
    if not callable(parse_fn):
        raise AssertionError(
            "constructed value has no callable parse: "
            f"{type(inst).__name__} {inst!r}"
        )
    applied = call(parse_fn, list(tokens))
    return require_parse_trees(applied)


def require_parse_trees(result: CallResult) -> list[Any]:
    """Return a list of parse trees, including a successful empty list.

    A product exception is a hard failure. Never maps an exception onto
    ``[]``. An unclassifiable value raises.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_parse_trees expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "parser did not yield a parse-tree set: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if _looks_like_constituent_tree(value):
        trees = [_as_constituent_tree(value)]
        print(f"parse set is a single tree (n=1)", flush=True)
        return trees
    if isinstance(value, (str, bytes, bytearray)):
        raise AssertionError(
            f"parser returned a string, not a parse-tree set: {value!r}"
        )
    if value is None:
        raise AssertionError(
            "parser returned None without raising; cannot classify as a "
            "parse-tree set"
        )
    try:
        items = list(value)
    except TypeError as exc:
        raise AssertionError(
            "parser did not return an iterable parse-tree set: "
            f"{type(value).__name__} {value!r}"
        ) from exc
    trees = [_as_constituent_tree(item) for item in items]
    print(f"parse set n={len(trees)}", flush=True)
    return trees


def require_parse_refused(result: CallResult) -> CallResult:
    """Uncovered-token refusal is an exception on the call or first iterate.

    A non-exception return — a tree, a string, ``None``, a tree set
    (including empty), or any other value — is not a refusal. Does not
    pin an exception type.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_parse_refused expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"parse refused {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _looks_like_constituent_tree(value):
        raise AssertionError(
            "parse succeeded with a constituent tree "
            f"(root={node_label(value)!r}); an uncovered-token path "
            "must not succeed, including as a one-tree set"
        )
    if isinstance(value, (str, bytes, bytearray)):
        raise AssertionError(
            "parse returned a string without raising; a non-exception "
            f"value is not a refusal: {value!r}"
        )
    if value is None:
        raise AssertionError(
            "parse returned None without raising; cannot classify as a "
            "parse refusal"
        )
    try:
        items = list(value)
    except TypeError as exc:
        raise AssertionError(
            f"parse returned {type(value).__name__} {value!r} without "
            "raising; cannot classify as a parse refusal"
        ) from exc
    except Exception as exc:
        raise AssertionError(
            "parse raised while the helper iterated a leftover lazy "
            f"value ({type(exc).__name__}: {exc}); harness did not "
            "capture the exception"
        ) from exc
    raise AssertionError(
        "parse returned a non-exception value "
        f"({type(value).__name__} n={len(items)}); an uncovered-token "
        "path must raise, including when the value is not a tree set"
    )


def constituent_children(tree: Any) -> list[Any]:
    """Immediate children of a labelled constituent. Read failure raises.

    A token-string leaf is not a traversable internal node.
    """
    if isinstance(tree, str):
        raise AssertionError(
            f"token-string leaf has no constituent children: {tree!r}"
        )
    if not _looks_like_constituent_tree(tree):
        raise AssertionError(
            "constituent node is not traversable: "
            f"{type(tree).__name__} {tree!r}"
        )
    try:
        return list(tree)
    except TypeError as exc:
        raise AssertionError(
            f"constituent children are not traversable: "
            f"{type(tree).__name__} {tree!r}"
        ) from exc


def constituent_child_at(tree: Any, index: int) -> Any:
    """Read one immediate child by position. Out of range raises; no ``None``."""
    children = constituent_children(tree)
    if index < 0 or index >= len(children):
        raise AssertionError(
            f"no immediate child at position {index} "
            f"(n_children={len(children)})"
        )
    child = children[index]
    print(
        f"child at {index}: kind={_constituent_kind(child)} value={child!r}",
        flush=True,
    )
    return child


def constituent_leaves(tree: Any) -> list[str]:
    """In-order token-string leaves. Read failure raises; no sentinel."""
    leaves: list[str] = []

    def walk(node: Any) -> None:
        kind = _constituent_kind(node)
        if kind == "leaf":
            leaves.append(node)
            return
        for child in constituent_children(node):
            walk(child)

    walk(tree)
    return leaves


def _iter_constituent_nodes(tree: Any) -> list[Any]:
    """This node and every labelled descendant. Walk failure raises."""
    nodes: list[Any] = []

    def walk(node: Any) -> None:
        kind = _constituent_kind(node)
        if kind == "leaf":
            return
        nodes.append(node)
        for child in constituent_children(node):
            walk(child)

    walk(tree)
    return nodes


def assert_constituent_covers(tree: Any, label: str, tokens: Sequence[str]) -> None:
    """Some node labelled *label* has exactly *tokens* as its full leaf sequence."""
    expected = list(tokens)
    for node in _iter_constituent_nodes(tree):
        if node_label(node) != label:
            continue
        got = constituent_leaves(node)
        if got == expected:
            print(f"constituent {label!r} covers {expected!r}", flush=True)
            return
    raise AssertionError(
        f"no node labelled {label!r} covers {expected!r}"
    )


def immediate_dominator_label(tree: Any, label: str, tokens: Sequence[str]) -> str:
    """Parent label of the node labelled *label* whose leaves are *tokens*.

    No such node, or a matching node that is the root, raises. When more
    than one node matches, the lowest (no matching child) is used.
    """
    expected = list(tokens)
    matches: list[tuple[Any, Any]] = []

    def walk(node: Any, parent: Any) -> None:
        kind = _constituent_kind(node)
        if kind == "leaf":
            return
        if node_label(node) == label and constituent_leaves(node) == expected:
            matches.append((node, parent))
        for child in constituent_children(node):
            walk(child, node)

    walk(tree, None)
    if not matches:
        raise AssertionError(
            f"no node labelled {label!r} covers {expected!r}"
        )
    match_ids = {id(node) for node, _parent in matches}
    lowest = [
        (node, parent)
        for node, parent in matches
        if not any(
            id(child) in match_ids for child in constituent_children(node)
        )
    ]
    if not lowest:
        raise AssertionError(
            f"matching {label!r} nodes covering {expected!r} have no lowest node"
        )
    node, parent = lowest[0]
    if parent is None:
        raise AssertionError(
            f"node labelled {label!r} covering {expected!r} is the root"
        )
    parent_label = node_label(parent)
    print(
        f"immediate dominator of {label!r} {expected!r} is {parent_label!r}",
        flush=True,
    )
    return parent_label


def require_tree(result: CallResult) -> Any:
    """Return one labelled, traversable constituent tree, or raise.

    Empty children are success. Never maps a failure onto an empty tree.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_tree expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "tree constructor did not yield a tree: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    tree = _as_constituent_tree(value)
    print(
        f"tree root={node_label(tree)!r} n_children={len(constituent_children(tree))}",
        flush=True,
    )
    return tree


def require_tree_refused(result: CallResult) -> CallResult:
    """Did not yield a labelled constituent tree.

    A tree with empty children is success and must raise. Does not pin
    an exception type. Unclassifiable outcomes raise.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_tree_refused expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"tree refused {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _looks_like_constituent_tree(value):
        raise AssertionError(
            "constructor yielded a labelled tree "
            f"(root={node_label(value)!r}, n_children="
            f"{len(constituent_children(value))}); a refused child list "
            "must not succeed, including as an empty-child tree"
        )
    if value is None:
        raise AssertionError(
            "constructor returned None without raising; cannot classify "
            "as a tree refusal"
        )
    if isinstance(value, (str, bytes, bytearray)) or _is_nonstring_sequence(value):
        print(
            f"constructor not a tree: {type(value).__name__} {value!r}",
            flush=True,
        )
        return result
    raise AssertionError(
        f"constructor returned {type(value).__name__} {value!r} without "
        "raising; cannot classify as a tree refusal"
    )


def assert_tree_refused(result: CallResult) -> CallResult:
    """Assert a tree constructor did not yield a labelled constituent tree.

    The ``assert`` is the test-visible tooth: a labelled tree — including
    an empty-child tree — fails. Does not pin an exception type.
    Unclassifiable outcomes raise rather than passing as a refusal.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"assert_tree_refused expects a CallResult; got {type(result)!r}"
        )
    if result.exception is None:
        value = result.value
        if value is None:
            raise AssertionError(
                "constructor returned None without raising; cannot classify "
                "as a tree refusal"
            )
        is_tree = _looks_like_constituent_tree(value)
        assert not is_tree, (
            "constructor yielded a labelled tree "
            f"(root={node_label(value)!r}, n_children="
            f"{len(constituent_children(value))}); a refused child list "
            "must not succeed, including as an empty-child tree"
        )
    return require_tree_refused(result)


def pretty_printed_tree(tree: Any) -> str:
    """Public pretty-print / string linearization. Empty or read failure raises."""
    pformat = getattr(tree, "pformat", None)
    if callable(pformat):
        result = call(pformat)
        if result.exception is not None:
            stderr = _stderr_snippet(result)
            raise AssertionError(
                "pretty-print failed: "
                f"{type(result.exception).__name__}: {result.exception}; "
                f"stderr={stderr!r}"
            )
        text = result.value
        if isinstance(text, str) and text.strip():
            print(f"pretty-printed {text!r}", flush=True)
            return text
        raise AssertionError(
            f"pretty-print returned empty or non-text: {text!r}"
        )
    for name in ("pprint", "pretty_print"):
        printer = getattr(tree, name, None)
        if not callable(printer):
            continue
        result = call(printer)
        if result.exception is not None:
            stderr = _stderr_snippet(result)
            raise AssertionError(
                "pretty-print failed: "
                f"{type(result.exception).__name__}: {result.exception}; "
                f"stderr={stderr!r}"
            )
        try:
            text = result.stdout_text
        except HarnessError:
            raise
        if text.strip():
            print(f"pretty-printed {text!r}", flush=True)
            return text
        raise AssertionError("pretty-print wrote empty text")
    text = str(tree)
    if not text.strip():
        raise AssertionError("tree string linearization is empty")
    print(f"pretty-printed {text!r}", flush=True)
    return text


def text_has_ordered_subsequence(text: str, parts: Sequence[str]) -> bool:
    """Whether *parts* appear in order in already-read *text* (gaps allowed).

    *text* that is not a ``str`` raises. A missing subsequence is
    ``False``, not a read failure.
    """
    if not isinstance(text, str):
        raise AssertionError(
            f"linearized tree text is not a str: {type(text).__name__} {text!r}"
        )
    pos = 0
    for part in parts:
        if not isinstance(part, str):
            raise AssertionError(
                f"subsequence part is not a str: {type(part).__name__} {part!r}"
            )
        found = text.find(part, pos)
        if found < 0:
            return False
        pos = found + len(part)
    return True


def tree_child_count(tree: Any) -> int:
    """Number of immediate children. Read failure raises."""
    n = len(constituent_children(tree))
    print(f"tree immediate-child count={n}", flush=True)
    return n


def generated_of(fn: Callable[..., Any], grammar: Any, **kwargs: Any) -> list[list[str]]:
    """Call a public generator entry and return token-list sentences.

    A product exception or a non-iterable value raises. An empty list is
    a successful empty generation, never a stand-in for failure.
    """
    result = call(fn, grammar, **kwargs)
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"generated_of expects call() to return CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "generator did not yield strings: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if isinstance(value, (str, bytes, bytearray)):
        raise AssertionError(
            f"generator returned a string, not a sequence of token lists: {value!r}"
        )
    if value is None:
        raise AssertionError(
            "generator returned None without raising; cannot classify "
            "as a generated set"
        )
    try:
        items = list(value)
    except TypeError as exc:
        raise AssertionError(
            "generator did not return an iterable of token lists: "
            f"{type(value).__name__} {value!r}"
        ) from exc
    sentences: list[list[str]] = []
    for item in items:
        if isinstance(item, (str, bytes, bytearray)):
            raise AssertionError(
                f"generated item is a string, not a token list: {item!r}"
            )
        if not _is_nonstring_sequence(item):
            raise AssertionError(
                "generated item is not a token list: "
                f"{type(item).__name__} {item!r}"
            )
        try:
            tokens = list(item)
        except TypeError as exc:
            raise AssertionError(
                f"generated item is not iterable: {type(item).__name__} {item!r}"
            ) from exc
        if not all(isinstance(tok, str) for tok in tokens):
            raise AssertionError(
                f"generated token list is not all strings: {tokens!r}"
            )
        sentences.append(tokens)
    print(f"generated {len(sentences)} strings", flush=True)
    return sentences


def _is_real_number(value: Any) -> bool:
    """True for a numeric scalar that can be an accuracy or probability.

    ``bool`` is excluded: it is a real-number subclass but not a score.
    """
    return isinstance(value, Real) and not isinstance(value, bool)


def _as_real_number(value: Any, *, what: str) -> float:
    """Return *value* as a float, or raise. Successful ``0`` is kept."""
    if not _is_real_number(value):
        raise AssertionError(
            f"{what} is not a real number: {type(value).__name__} {value!r}"
        )
    return float(value)


def require_trained_classifier(result: CallResult) -> Any:
    """Return a trained classifier, or raise.

    A product exception, or a value with no callable classify entry, is
    a hard failure. Never maps a failure onto ``None``. Does not require
    a probability-distribution entry (decision trees need not have one).
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_trained_classifier expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "training did not yield a classifier: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    inst = result.value
    classify_fn = getattr(inst, "classify", None)
    if not callable(classify_fn):
        raise AssertionError(
            "trained value has no callable classify: "
            f"{type(inst).__name__} {inst!r}"
        )
    print(f"trained classifier type={type(inst).__name__}", flush=True)
    return inst


def classified_label(classifier: Any, featureset: Any) -> Any:
    """Call the classify entry and return the label.

    A product exception, or ``None``, is a hard failure. Never maps a
    failure onto ``None`` or onto a training label. An empty string is a
    successful label, not a sentinel.
    """
    classify_fn = getattr(classifier, "classify", None)
    if not callable(classify_fn):
        raise AssertionError(
            "classifier has no callable classify: "
            f"{type(classifier).__name__} {classifier!r}"
        )
    result = call(classify_fn, featureset)
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"classified_label expects call() to return CallResult; "
            f"got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "classify did not return a label: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if value is None:
        raise AssertionError(
            "classify returned None without raising; cannot classify as a label"
        )
    print(f"classified {featureset!r} -> {value!r}", flush=True)
    return value


def _probe_label_from_dist(dist: Any) -> Any:
    """A label the distribution can name, or raise.

    Tries the public samples / max entries, then iteration. Does not
    invent a label. A read failure raises; it is not mapped to ``None``.
    """
    samples_fn = getattr(dist, "samples", None)
    if callable(samples_fn):
        sampled = call(samples_fn)
        if sampled.exception is not None:
            stderr = _stderr_snippet(sampled)
            raise AssertionError(
                "reading probability-distribution samples failed: "
                f"{type(sampled.exception).__name__}: {sampled.exception}; "
                f"stderr={stderr!r}"
            )
        value = sampled.value
        if isinstance(value, (str, bytes, bytearray)):
            raise AssertionError(
                f"probability-distribution samples is a string: {value!r}"
            )
        if value is None:
            raise AssertionError(
                "probability-distribution samples returned None without raising"
            )
        try:
            items = list(value)
        except TypeError as exc:
            raise AssertionError(
                "probability-distribution samples are not iterable: "
                f"{type(value).__name__} {value!r}"
            ) from exc
        if items:
            return items[0]
    max_fn = getattr(dist, "max", None)
    if callable(max_fn):
        topped = call(max_fn)
        if topped.exception is not None:
            stderr = _stderr_snippet(topped)
            raise AssertionError(
                "reading probability-distribution max failed: "
                f"{type(topped.exception).__name__}: {topped.exception}; "
                f"stderr={stderr!r}"
            )
        if topped.value is not None:
            return topped.value
    if _is_nonstring_sequence(dist) or isinstance(dist, dict):
        try:
            items = list(dist)
        except TypeError as exc:
            raise AssertionError(
                "probability distribution is not iterable for a probe label: "
                f"{type(dist).__name__} {dist!r}"
            ) from exc
        if items:
            return items[0]
    raise AssertionError(
        "probability distribution cannot yield a named label: "
        f"{type(dist).__name__} {dist!r}"
    )


def label_probability(dist: Any, label: Any) -> float:
    """Read P(*label*) as a real number.

    Read failure raises. A successfully read ``0`` is returned as ``0``,
    never as a stand-in for "could not look up". Does not pin a
    distribution type name.
    """
    what = f"probability for {label!r}"
    prob_fn = getattr(dist, "prob", None)
    if callable(prob_fn):
        result = call(prob_fn, label)
        if result.exception is not None:
            stderr = _stderr_snippet(result)
            raise AssertionError(
                f"reading {what} failed: "
                f"{type(result.exception).__name__}: {result.exception}; "
                f"stderr={stderr!r}"
            )
        value = _as_real_number(result.value, what=what)
        print(f"{what}={value!r}", flush=True)
        return value
    getter = getattr(dist, "__getitem__", None)
    if callable(getter):
        result = call(getter, label)
        if result.exception is not None:
            stderr = _stderr_snippet(result)
            raise AssertionError(
                f"reading {what} failed: "
                f"{type(result.exception).__name__}: {result.exception}; "
                f"stderr={stderr!r}"
            )
        value = _as_real_number(result.value, what=what)
        print(f"{what}={value!r}", flush=True)
        return value
    raise AssertionError(
        f"probability distribution cannot be queried for {label!r}: "
        f"{type(dist).__name__} {dist!r}"
    )


def require_label_probdist(result: CallResult) -> Any:
    """Return a label probability distribution, or raise.

    A product exception is a hard failure. The object must yield a real
    probability for at least one named label; unclassifiable values
    raise. Never maps a failure onto a zero-probability stand-in.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_label_probdist expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "probability-distribution entry did not yield a distribution: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    dist = result.value
    if dist is None:
        raise AssertionError(
            "probability-distribution entry returned None without raising"
        )
    probe = _probe_label_from_dist(dist)
    p = label_probability(dist, probe)
    print(
        f"probdist probe label={probe!r} p={p!r} type={type(dist).__name__}",
        flush=True,
    )
    return dist


def listed_labels(classifier: Any) -> list[Any]:
    """Label-name sequence from the classifier's public list entry.

    A string is not a list of names (it would iterate as characters).
    Read failure raises. An empty list is returned only when the
    product actually yielded one.
    """
    labels_fn = getattr(classifier, "labels", None)
    if not callable(labels_fn):
        raise AssertionError(
            "classifier has no callable labels: "
            f"{type(classifier).__name__} {classifier!r}"
        )
    result = call(labels_fn)
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"listed_labels expects call() to return CallResult; "
            f"got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "listing labels failed: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = result.value
    if isinstance(value, (str, bytes, bytearray)):
        raise AssertionError(
            f"listed labels is a string, not a sequence of names: {value!r}"
        )
    if not _is_nonstring_sequence(value):
        raise AssertionError(
            "listed labels is not a sequence of names: "
            f"{type(value).__name__} {value!r}"
        )
    try:
        items = list(value)
    except TypeError as exc:
        raise AssertionError(
            "listed labels are not iterable: "
            f"{type(value).__name__} {value!r}"
        ) from exc
    print(f"listed labels={items!r}", flush=True)
    return items


def accuracy_number(result: CallResult) -> float:
    """Return a successful accuracy real (including ``0``), or raise.

    A product exception is a hard failure. A non-number is a hard
    failure. Never maps a failure onto ``0``.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"accuracy_number expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            "accuracy helper did not return a number: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = _as_real_number(result.value, what="accuracy")
    print(f"accuracy={value!r}", flush=True)
    return value


def require_accuracy_refused(result: CallResult) -> CallResult:
    """Did not yield a successful accuracy number.

    A real number — including ``0`` — is success and must raise. ``None``
    is not a number and counts as unsuccessful. Other unclassifiable
    scalars raise. Does not pin an exception type.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_accuracy_refused expects a CallResult; "
            f"got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"accuracy refused {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _is_real_number(value):
        raise AssertionError(
            "accuracy succeeded with a number "
            f"{value!r}; a mismatched-length path must not succeed, "
            "including as 0"
        )
    if value is None:
        print("accuracy returned None (not a number)", flush=True)
        return result
    raise AssertionError(
        f"accuracy returned {type(value).__name__} {value!r} without "
        "raising; cannot classify as an accuracy refusal"
    )


def score_number(result: CallResult, *, what: str = "score") -> float:
    """Return a successful real score (including ``0``), or raise.

    A product exception is a hard failure. A non-number is a hard
    failure. Never maps a failure onto ``0``. ``bool`` is not a score
    (same rule as ``_as_real_number``).
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"score_number expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        raise AssertionError(
            f"{what} did not return a number: "
            f"{type(result.exception).__name__}: {result.exception}; "
            f"stderr={stderr!r}"
        )
    value = _as_real_number(result.value, what=what)
    print(f"{what}={value!r}", flush=True)
    return value


def require_no_score(result: CallResult, *, what: str = "score") -> CallResult:
    """Did not yield a successful real score.

    A real number — including ``0`` — is success and must raise. ``None``
    is not a number and counts as unsuccessful. Other unclassifiable
    scalars raise. Does not pin an exception type. Never maps an
    exception onto ``0``.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"require_no_score expects a CallResult; got {type(result)!r}"
        )
    if result.exception is not None:
        stderr = _stderr_snippet(result)
        print(
            f"{what} absent {type(result.exception).__name__}: "
            f"{result.exception}; stderr={stderr!r}",
            flush=True,
        )
        return result
    value = result.value
    if _is_real_number(value):
        raise AssertionError(
            f"{what} succeeded with a number {value!r}; "
            "an absent or refused path must not succeed, including as 0"
        )
    if value is None:
        print(f"{what} returned None (not a number)", flush=True)
        return result
    raise AssertionError(
        f"{what} returned {type(value).__name__} {value!r} without "
        "raising; cannot classify as a score absence"
    )


def assert_no_score(result: CallResult, *, what: str = "score") -> CallResult:
    """Assert the call did not yield a successful real score.

    The ``assert`` is the test-visible tooth: a real number — including
    ``0`` — fails. ``None`` is not a number and counts as absence.
    Does not pin an exception type. Unclassifiable scalars raise rather
    than passing as absence.
    """
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"assert_no_score expects a CallResult; got {type(result)!r}"
        )
    if result.exception is None:
        value = result.value
        is_number = _is_real_number(value)
        assert not is_number, (
            f"{what} succeeded with a number {value!r}; "
            "an absent or refused path must not succeed, including as 0"
        )
    return require_no_score(result)


# ---------------------------------------------------------------------------
# Packaged-resource fixtures.
#
# Every test runs in a fresh interpreter (see conftest.py), so no model
# loaded by an earlier test can satisfy or hide a resource condition. A
# test lays out a workspace data directory by copying resources from the
# environment's resource directory, then points the product's public
# search list at that directory (or at nothing) before any product call.
# ---------------------------------------------------------------------------

import os as _os

# Where the environment installs the pinned public resources
# (source/env/resources.json "destination"). Overridable for local runs.
HOST_RESOURCE_DIR = Path(_os.environ.get("CB_HOST_RESOURCE_DIR", "/opt/models"))


def _host_resource(rel: str) -> Path:
    src = HOST_RESOURCE_DIR / rel.strip("/")
    try:
        if src.is_dir():
            if not any(src.iterdir()):
                raise HarnessError(f"host resource directory is empty: {src}")
        elif not src.is_file() or src.stat().st_size == 0:
            raise HarnessError(f"host resource is missing or empty: {src}")
    except OSError as exc:
        raise HarnessError(f"cannot read host resource {src}: {exc}") from exc
    return src


def install_host_resource(ws: Any, rel: str, *, label: str) -> Path:
    """Copy one environment resource into *ws.data* at its resource name.

    Copy failure raises. Never downloads. Never skips.
    """
    src = _host_resource(rel)
    dest = Path(ws.data) / rel.strip("/")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copyfile(src, dest)
    except OSError as exc:
        raise HarnessError(f"failed to copy {label} into the workspace: {exc}") from exc
    print(f"installed {label} at {dest}", flush=True)
    return dest


def install_english_punkt(ws: Any) -> Path:
    return install_host_resource(ws, _ENGLISH_SENTENCE_RESOURCE, label="English sentence model")


def install_stopwords(ws: Any, language: str) -> Path:
    return install_host_resource(
        ws, f"{_STOPWORDS_CORPUS_RESOURCE}/{language}", label=f"{language!r} stopwords list"
    )


def install_perceptron(ws: Any, language: str) -> Path:
    return install_host_resource(
        ws, _perceptron_resource(language), label=f"{language!r} averaged perceptron tagger"
    )


def install_universal_tagset(ws: Any) -> Path:
    return install_host_resource(ws, _UNIVERSAL_TAGSET_RESOURCE, label="universal tagset tables")


def install_ne_chunker(ws: Any) -> Path:
    return install_host_resource(ws, _NE_CHUNKER_RESOURCE, label="named-entity chunker")


def install_english_words(ws: Any) -> Path:
    return install_host_resource(ws, _ENGLISH_WORDS_RESOURCE, label="English wordlist")


@contextmanager
def bound_resource_path(ws: Any, *, present: bool = True) -> Iterator[None]:
    """Set the product search list to *ws.data* (present) or empty (absent).

    Uses only the public, caller-settable search list. Restores it on exit.
    """
    from lingora import data

    search = getattr(data, "path", None)
    if not isinstance(search, list):
        raise HarnessError(
            "product resource search list is not a mutable list; "
            f"got {type(search)!r}"
        )
    items = [str(Path(ws.data).resolve())] if present else []
    with replace_list(search, items):
        yield
