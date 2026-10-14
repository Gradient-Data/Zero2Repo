# feature: F04
"""Observation helpers for the membundle search command and membundle_search tool (FP-04).

Helpers raise ``HarnessError`` when a query cannot be classified, and
``AssertionError`` when a classified observation misses a carrier the
tests require. They never return ``None`` / ``{}`` / ``""`` / ``[]`` to
mean "could not look".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from _harness import (
    HarnessError,
    McpBatchResult,
    RunResult,
    Workspace,
    json_stdout,
    rpc_request,
)
from F01_helpers import (
    combined_report,
    split_yaml_frontmatter,
    unique_leaf,
)
from F03_helpers import (
    concept_spec,
    mcp_is_protocol_error,
    mcp_is_tool_error,
    mcp_reply_for_id,
    render_concept_markdown,
    snapshot_tree,
    unique_tokens,
    write_bundle,
)

# Keyword fields a hit may name. The path channel is not a member of this set.
MATCHED_FIELD_SET = frozenset({"title", "tags", "description", "id", "body"})
# The path-hit channel token.
CODE_REF_MATCH_CHANNEL = "code_refs"
# The six matched-field tokens of ``matched_on`` and the human ``Matches:`` line.
HIT_MATCH_TOKENS = MATCHED_FIELD_SET | {CODE_REF_MATCH_CHANNEL}

# Human ``search`` output forms.
_HUMAN_HIT_LINE = re.compile(
    r"^ *(\d+)\. +\[(constraint|hold|context)\] +\[([^\]]*)\] +(\S.*)$"
)


def _is_zero_hit_report(lines: list[str]) -> bool:
    """Contract Output forms, ``search`` (human): zero hits is exactly one
    non-empty line (wording free) that does not have the form of a block's
    first line."""
    return (
        len(lines) == 2
        and lines[1] == ""
        and lines[0].strip() != ""
        and _HUMAN_HIT_LINE.match(lines[0]) is None
    )
_HUMAN_INDENT = "    "
_HUMAN_MATCHES = "    Matches: "

# Command-line failure classes of ``search``.
USAGE_FAILURE_STATUS = 1
USAGE_LITERAL = "Usage:"
LOAD_FAILURE_STATUS = 2
LOAD_FAILURE_PREFIX = "Error loading bundle: "
# Tool-level failure text when a named bundle cannot be loaded.
TOOL_LOAD_FAILURE_PREFIX = "Failed to load bundle from "

GOVERNANCE_TOKENS = frozenset({"hold", "constraint", "context"})

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_EXECUTED = (
    "the call was never executed; search results are missing"
)


def _workdir_has_product_sources(root: Path) -> bool:
    """True when *root* is a product tree: a Go module (``go.mod``) with a root
    ``Makefile`` (Contract "Build": ``make build`` at the root writes
    ``bin/membundle``). The Makefile's text is not read."""
    return (root / "Makefile").is_file() and (root / "go.mod").is_file()


def _stage_writable_sources(root: Path) -> Path:
    """Copy *root* to a writable directory, excluding any existing binary.

    The judge cwd may be a read-only filesystem. ``make build`` must not
    run there, and a binary already present under that cwd must not be
    reused.
    """
    stage = Path(tempfile.mkdtemp(prefix="membundle-build-"))
    shutil.copytree(
        root,
        stage,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "bin"),
    )
    # copytree preserves a read-only source mode, including on the stage
    # root, which then rejects mkdir bin. The copy itself must be writable.
    for dirpath, _dirnames, filenames in os.walk(stage):
        os.chmod(dirpath, os.stat(dirpath).st_mode | 0o700)
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            os.chmod(path, path.stat().st_mode | 0o600)
    prebuilt = stage / _BIN_REL
    if prebuilt.is_symlink() or prebuilt.exists():
        prebuilt.unlink()
    return stage


def _run_product_build(root: Path) -> bool:
    """Run ``GOFLAGS=-buildvcs=false make build`` in a writable source copy.

    *root* is not the judge cwd. Returns True only when ``make`` exits 0.
    A non-zero exit is logged and is not the test result. ``make`` itself
    missing is not a successful build. Does not search ``PATH`` or honor
    ``PRODUCT_BIN``.
    """
    env = dict(os.environ)
    env.pop("PRODUCT_BIN", None)
    env["GOFLAGS"] = "-buildvcs=false"
    print(f"[F04] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
    try:
        completed = subprocess.run(
            ["make", "build"],
            cwd=str(root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        print(f"[F04] make build could not start: {exc}", flush=True)
        return False
    print(f"[F04] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F04] make build stdout={stdout[-2000:]!r} "
            f"stderr={stderr[-2000:]!r}",
            flush=True,
        )
        return False
    return True


def _workdir_membundle() -> Path | None:
    """Return the ``bin/membundle`` this build just produced.

    When the pytest cwd contains the product sources, copies them to a
    writable directory and runs ``GOFLAGS=-buildvcs=false make build``
    there. Does not search ``PATH``, does not honor ``PRODUCT_BIN``, does
    not build in the judge cwd, and does not use a binary this build did
    not just produce. An empty cwd, or a build that does not produce an
    executable, returns None so the caller fails because the command
    results are missing.
    """
    global _BUILD_DONE, _BUILT_BIN
    with _BUILD_LOCK:
        if not _BUILD_DONE:
            root = Path.cwd().resolve()
            built: Path | None = None
            if _workdir_has_product_sources(root):
                stage = _stage_writable_sources(root)
                if _run_product_build(stage):
                    candidate = stage / _BIN_REL
                    resolved = candidate.resolve()
                    if (
                        candidate.is_file()
                        and os.access(candidate, os.X_OK)
                        and resolved.is_relative_to(stage.resolve())
                    ):
                        built = resolved
            _BUILT_BIN = built
            _BUILD_DONE = True
            print(f"[F04] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_search_binary() -> Path:
    """Single resolver for every F04 search-command and search-tool call.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return a synthetic non-zero
    result: F04 usage assertions accept any non-zero exit and would then
    pass on an empty workspace.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it search never runs and its results are missing.
    assert binary is not None, _NEVER_EXECUTED
    return binary


def _raise_if_search_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-executed assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F04): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_EXECUTED) from None


@dataclass(frozen=True)
class McpSearchOutcome:
    """Classified JSON-RPC reply to one membundle_search tools/call.

    A missing reply for the requested id raises ``HarnessError`` before
    this object is built. None of the fields is a sentinel for "no reply".
    """

    batch: McpBatchResult
    reply: dict[str, Any]
    payload: Any
    report_text: str


def compact_token(prefix: str) -> str:
    """Runtime-unique alphanumeric token (no hyphen split points)."""
    token = unique_leaf(prefix).replace("-", "")
    if not token or not token.isalnum():
        raise HarnessError(f"compact token is not alphanumeric: {token!r}")
    if token in MATCHED_FIELD_SET or token in GOVERNANCE_TOKENS:
        raise HarnessError(f"compact token collides with a reserved set member: {token!r}")
    return token


def unique_compact(*prefixes: str) -> tuple[str, ...]:
    """Runtime-unique alphanumeric tokens that are not substrings of each other."""
    tokens = [compact_token(prefix) for prefix in prefixes]
    for index, left in enumerate(tokens):
        for other, right in enumerate(tokens):
            if index == other:
                continue
            if left in right or right in left:
                raise HarnessError(
                    f"generated compact tokens overlap: {left!r} vs {right!r}"
                )
    return tuple(tokens)


def other_letter_case(token: str) -> str:
    """Swap every letter in *token* to the other letter case.

    Digits stay. The result is a different spelling of the same letters
    and digits, so a query built from it differs in letter case from the
    stored token and still casefolds to that token. A token with no
    letter cannot show that difference; that is a fixture error.
    """
    if not isinstance(token, str) or not token:
        raise HarnessError(f"other letter case needs a token: {token!r}")
    if not token.isalnum():
        raise HarnessError(
            f"other letter case token must stay one term: {token!r}"
        )
    if not any(ch.isalpha() for ch in token):
        raise HarnessError(
            f"token has no letter whose case can differ: {token!r}"
        )
    flipped_chars: list[str] = []
    for ch in token:
        if ch.isupper():
            flipped_chars.append(ch.lower())
        elif ch.islower():
            flipped_chars.append(ch.upper())
        else:
            flipped_chars.append(ch)
    flipped = "".join(flipped_chars)
    if flipped == token or flipped.casefold() != token.casefold():
        raise HarnessError(
            f"letter-case swap did not change only case: {token!r} -> {flipped!r}"
        )
    return flipped


# One lowercase non-ASCII letter whose other case is a different letter.
# Cyrillic ya folds under simple Unicode case mapping. The fixture uses it
# so a fold that only rewrites ASCII letters leaves this letter unchanged.
_NON_ASCII_CASED_LETTER = "\u044f"


def other_case_token_with_non_ascii_letter(
    ascii_base: str,
    *,
    prefix_tail: str | None = None,
) -> tuple[str, str]:
    """Return ``(query, stored)`` for one case-insensitive term.

    *query* is *ascii_base* plus one lowercase non-ASCII letter. *stored*
    is the other letter case of that whole term, so the letters whose
    case differs include a non-ASCII letter. When *prefix_tail* is given,
    it is appended to *stored* and the stored token starts with the term
    and is longer than the term. Both strings stay one term. Does not
    call the product.
    """
    letter = _NON_ASCII_CASED_LETTER
    if (
        len(letter) != 1
        or letter.isascii()
        or not letter.isalpha()
        or not letter.islower()
        or letter.upper() == letter
        or letter.upper().lower() != letter
        or letter.casefold() != letter.upper().casefold()
    ):
        raise HarnessError(
            f"non-ASCII cased letter {letter!r} has no other letter case"
        )
    if (
        not isinstance(ascii_base, str)
        or not ascii_base
        or not ascii_base.isascii()
        or not ascii_base.isalnum()
        or not any(ch.isalpha() for ch in ascii_base)
    ):
        raise HarnessError(
            f"ASCII base {ascii_base!r} is not one letter-digit token "
            "with a letter"
        )
    query = ascii_base + letter
    stored_head = other_letter_case(query)
    if not any(
        left != right and not left.isascii() and left.isalpha()
        for left, right in zip(query, stored_head)
    ):
        raise HarnessError(
            "non-ASCII letter case did not differ: "
            f"{query!r} -> {stored_head!r}"
        )
    if prefix_tail is None:
        return query, stored_head
    if (
        not isinstance(prefix_tail, str)
        or not prefix_tail
        or not prefix_tail.isascii()
        or not prefix_tail.isalnum()
    ):
        raise HarnessError(
            f"prefix tail {prefix_tail!r} is not one ASCII letter-digit token"
        )
    if query.casefold() in prefix_tail.casefold():
        raise HarnessError(
            f"prefix tail {prefix_tail!r} already contains the term {query!r}"
        )
    stored = stored_head + prefix_tail
    if (
        stored.casefold() == query.casefold()
        or not stored.casefold().startswith(query.casefold())
        or not stored.startswith(stored_head)
    ):
        raise HarnessError(
            f"stored token {stored!r} does not start with term {query!r} "
            "as a longer token"
        )
    return query, stored


# Joiners this suite already searches as term splits: comma, hyphen, period,
# underscore, slash, and space (other queries are space-separated). A mark
# outside this set is still a split. Letters and digits are not members.
_CLOSED_TERM_SPLITTERS = frozenset({",", "-", ".", "_", "/", " "})


def term_splitter_outside_closed_set() -> str:
    """One non-letter, non-digit mark the closed splitter set does not contain.

    The keyword-search rule keeps letters and digits, including non-ASCII
    letters, inside a term, and splits on every other character. Plus is
    none of comma, hyphen, period, underscore, slash, or space. A tokenizer
    that splits only on that closed set keeps this mark inside one term.
    """
    mark = "+"
    if (
        len(mark) != 1
        or mark.isalnum()
        or mark.isspace()
        or mark in _CLOSED_TERM_SPLITTERS
    ):
        raise HarnessError(
            f"term splitter {mark!r} is a letter, a digit, whitespace, "
            f"or an already-searched splitter"
        )
    return mark


def non_ascii_term_splitter() -> str:
    """One non-ASCII character that is not a letter and not a digit.

    Letters and digits, including non-ASCII letters, stay inside a term.
    Every other character splits terms. The mark outside the closed
    joiner set is ASCII plus. A tokenizer that keeps every non-ASCII
    character inside a term still splits on plus and still keeps a
    non-ASCII letter inside a term. Middle dot is neither.
    """
    mark = "\u00b7"
    if (
        len(mark) != 1
        or mark.isascii()
        or mark.isalpha()
        or mark.isdigit()
        or mark.isalnum()
        or mark.isspace()
        or mark in _CLOSED_TERM_SPLITTERS
        or mark == term_splitter_outside_closed_set()
    ):
        raise HarnessError(
            f"non-ASCII term splitter {mark!r} is ASCII, a letter, a digit, "
            "whitespace, or an already-searched splitter"
        )
    return mark


def require_non_ascii_letters_then_ascii_tail(title: str, tail: str) -> str:
    """Return *title* when non-ASCII letters are followed by ASCII *tail*.

    Every character is a letter or a digit, so the whole string is one
    term and *tail* is not a prefix of that term. The head is non-ASCII
    letters. Splitting on every non-ASCII character leaves only *tail*.
    Raises ``HarnessError`` when the fixture does not have that shape.
    Does not call the product.
    """
    if not tail or not tail.isascii() or not tail.isalnum():
        raise HarnessError(
            f"ASCII tail {tail!r} is empty or not an ASCII letter-digit token"
        )
    if not title.endswith(tail) or len(title) <= len(tail):
        raise HarnessError(
            f"title {title!r} does not end with a non-empty head plus {tail!r}"
        )
    head = title[: -len(tail)]
    if not head or head.isascii() or not all(ch.isalpha() for ch in head):
        raise HarnessError(
            f"title head {head!r} is not one or more non-ASCII letters"
        )
    if not title.isalnum():
        raise HarnessError(
            f"title {title!r} contains a character that splits a term"
        )
    if title.casefold().startswith(tail.casefold()):
        raise HarnessError(
            f"ASCII tail {tail!r} is a prefix of the whole title {title!r}"
        )
    ascii_runs: list[str] = []
    buf: list[str] = []
    for ch in title:
        if ch.isascii():
            buf.append(ch)
        elif buf:
            ascii_runs.append("".join(buf))
            buf = []
    if buf:
        ascii_runs.append("".join(buf))
    if ascii_runs != [tail]:
        raise HarnessError(
            f"splitting {title!r} on every non-ASCII character does not "
            f"leave only the ASCII tail {tail!r}; runs={ascii_runs!r}"
        )
    return title


# One non-ASCII letter. Greek alpha is a letter and not a digit, so a
# term keeps it. It is not the fixed-sample head and not the cased
# Cyrillic letter already used for case folding.
_NON_ASCII_TERM_LETTER = "\u03b1"


def query_joined_on_non_ascii_letter(left: str, right: str) -> str:
    """Join two ASCII letter-digit pieces with one non-ASCII letter.

    The returned query has that letter between *left* and *right* and no
    other splitter, so the whole string is one term. Splitting that letter
    out, including giving each non-ASCII letter its own term while each
    ASCII run stays grouped, leaves *left* and *right* as separate terms.
    Raises ``HarnessError`` when the pieces do not have that shape. Does
    not call the product.
    """
    letter = _NON_ASCII_TERM_LETTER
    if (
        len(letter) != 1
        or letter.isascii()
        or not letter.isalpha()
        or letter.isdigit()
        or letter.isspace()
        or letter in _CLOSED_TERM_SPLITTERS
        or letter == non_ascii_term_splitter()
    ):
        raise HarnessError(
            f"non-ASCII term letter {letter!r} is not one letter that "
            "stays inside a term"
        )
    for piece in (left, right):
        if (
            not isinstance(piece, str)
            or not piece
            or not piece.isascii()
            or not piece.isalnum()
        ):
            raise HarnessError(
                f"piece {piece!r} is not one ASCII letter-digit token"
            )
    if left in right or right in left:
        raise HarnessError(
            f"pieces overlap, so one side title would match the other: "
            f"{left!r} vs {right!r}"
        )
    query = f"{left}{letter}{right}"
    if any(ch.isspace() for ch in query) or not query.isalnum():
        raise HarnessError(
            f"joined query {query!r} contains a character that splits a term"
        )
    if [ch for ch in query if not ch.isascii()] != [letter]:
        raise HarnessError(
            f"joined query {query!r} does not contain exactly one "
            f"non-ASCII letter {letter!r}"
        )
    if query.split(letter) != [left, right]:
        raise HarnessError(
            f"splitting {query!r} on the non-ASCII letter does not yield "
            f"{left!r} and {right!r}"
        )
    grouped: list[str] = []
    buf: list[str] = []
    for ch in query:
        if ch.isascii() and ch.isalnum():
            buf.append(ch)
            continue
        if buf:
            grouped.append("".join(buf))
            buf = []
        if not ch.isascii() and ch.isalpha():
            grouped.append(ch)
            continue
        raise HarnessError(
            f"joined query {query!r} has a splitter other than the "
            f"non-ASCII letter: {ch!r}"
        )
    if buf:
        grouped.append("".join(buf))
    if grouped != [left, letter, right]:
        raise HarnessError(
            f"giving each non-ASCII letter its own term in {query!r} "
            f"did not yield the two pieces around {letter!r}; "
            f"terms={grouped!r}"
        )
    return query


def space_free_joined_terms(terms: Sequence[str], splitter: str) -> str:
    """Join *terms* on *splitter* into one whitespace-free query.

    The 50-term cap is applied after splitting, and splitting is every
    non-letter non-digit, not spaces alone. A query this helper returns
    is a single whitespace-separated word of at most 1000 characters, so
    the 1000-character cut is not what drops a later term, and a cap that
    keeps the first 50 whitespace-separated words still holds every term.
    *splitter* is not a letter, a digit, or whitespace. Each term is
    alphanumeric, so the only split points are the joiner.
    """
    if len(splitter) != 1 or splitter.isalnum() or splitter.isspace():
        raise HarnessError(
            f"term joiner {splitter!r} must be one non-letter non-digit "
            "non-whitespace character"
        )
    if not terms:
        raise HarnessError("space-free term query needs at least one term")
    for term in terms:
        if not term or not term.isalnum():
            raise HarnessError(
                f"term {term!r} is empty or not alphanumeric; it would add "
                "a split point or a whitespace word"
            )
        if splitter in term:
            raise HarnessError(
                f"term {term!r} already contains joiner {splitter!r}"
            )
    query = splitter.join(terms)
    if any(ch.isspace() for ch in query) or len(query.split()) != 1:
        raise HarnessError(
            f"joined query is not one whitespace-separated word: {query!r}"
        )
    if len(query) > 1000:
        raise HarnessError(
            f"joined query is {len(query)} characters; the 1000-character "
            "cut would hide whether term 51 was ignored"
        )
    if query.split(splitter) != list(terms):
        raise HarnessError(
            f"joined query does not split back into the given terms on "
            f"{splitter!r}"
        )
    return query


def _alnum_parts(text: str) -> list[str]:
    """Letters and digits stay in a part; every other character splits."""
    return re.findall(r"[0-9A-Za-z]+", text)


def query_cut_inside_one_term(kept_prefix: str, discarded: str) -> str:
    """Query whose 1000-character cut falls inside one term.

    Truncation keeps the first 1000 characters and then splits that
    prefix. *kept_prefix* is the part of the straddling term that remains
    inside the window; *discarded* is the rest of that same term, past
    the cut. A filler term and one space sit in front so they do not glue
    onto *kept_prefix*. The full query is longer than 1000 characters and
    is ASCII, so a character cut and a byte cut land on the same index.
    Splitting the uncut query does not yield *kept_prefix* on its own.
    """
    if not kept_prefix or not discarded:
        raise HarnessError(
            "a cut inside one term needs a non-empty kept prefix and a "
            f"non-empty discarded continuation: {kept_prefix!r} / {discarded!r}"
        )
    if not kept_prefix.isascii() or not kept_prefix.isalnum():
        raise HarnessError(
            f"kept prefix {kept_prefix!r} is not an ASCII letter-digit term"
        )
    if not discarded.isascii() or not discarded.isalnum():
        raise HarnessError(
            f"discarded continuation {discarded!r} is not an ASCII "
            "letter-digit term"
        )
    folded_kept = kept_prefix.casefold()
    folded_discarded = discarded.casefold()
    if folded_kept in folded_discarded or folded_discarded in folded_kept:
        raise HarnessError(
            f"kept prefix {kept_prefix!r} and discarded continuation "
            f"{discarded!r} overlap, so either title would match the other term"
        )
    # One filler character, a space, and the kept prefix occupy the window.
    if len(kept_prefix) > 998:
        raise HarnessError(
            f"kept prefix length {len(kept_prefix)} leaves no room for a "
            "separate filler term inside 1000 characters"
        )
    filler = "x"
    if filler in folded_kept or filler in folded_discarded:
        raise HarnessError(
            f"filler {filler!r} appears inside a distinctive term"
        )
    pad = 1000 - len(kept_prefix) - 1
    query = (filler * pad) + " " + kept_prefix + discarded
    if len(query.encode("utf-8")) != len(query):
        raise HarnessError("cut-inside-term query is not ASCII")
    if len(query) <= 1000:
        raise HarnessError(
            f"cut-inside-term query is only {len(query)} characters"
        )
    window = query[:1000]
    if window != (filler * pad) + " " + kept_prefix:
        raise HarnessError(
            "first 1000 characters are not the filler term, a space, and "
            f"the kept prefix: {window[-len(kept_prefix) - 8:]!r}"
        )
    if query[1000:] != discarded:
        raise HarnessError(
            "characters past the cut are not the discarded continuation"
        )
    start = pad + 1
    if not 0 <= start < 1000:
        raise HarnessError(
            f"straddling term starts at {start}, which is not inside the window"
        )
    if query[start : 1000 + len(discarded)] != kept_prefix + discarded:
        raise HarnessError("straddling term is not the kept prefix plus the tail")
    if _alnum_parts(window) != [filler * pad, kept_prefix]:
        raise HarnessError(
            "truncated query did not split into the filler term and the "
            f"kept prefix: {_alnum_parts(window)!r}"
        )
    if _alnum_parts(query) != [filler * pad, kept_prefix + discarded]:
        raise HarnessError(
            "uncut query did not keep the straddling piece as one term: "
            f"{_alnum_parts(query)!r}"
        )
    return query


# Letters outside hexadecimal, so a uuid token does not start with them.
# ``x`` is the filler beside the 1000-character boundary and is not a candidate.
_BOUNDARY_TERM_LETTERS = "qzwjvkb"


def term_character_outside_fixture_prefixes(*texts: str) -> str:
    """One ASCII letter that no token in *texts* starts with.

    A one-letter query term matches a field token that equals it or starts
    with it. The letter is not the filler beside the 1000-character
    boundary, so that filler term does not match a title equal to the
    letter, and the letter does not match the filler. Raises when every
    candidate is already the start of a fixture token.
    """
    occupied: set[str] = set()
    for text in texts:
        if not isinstance(text, str) or text == "":
            raise HarnessError(
                "boundary-term scan needs a non-empty fixture text: "
                f"{text!r}"
            )
        for part in _alnum_parts(text):
            occupied.add(part[0].casefold())
    occupied.add("x")
    for letter in _BOUNDARY_TERM_LETTERS:
        if letter not in occupied:
            return letter
    raise HarnessError(
        "every boundary-term letter starts a fixture token: "
        f"{sorted(occupied)!r}"
    )


def queries_with_term_starting_at_position_1000(term: str) -> tuple[str, str]:
    """Return ``(exact_1000, longer)`` with *term* beginning at position 1000.

    Position 1000 is the 1000th character, the last character a
    1000-character window keeps. A splitter sits immediately before it.
    *term* is that one character, and the concept title that must hit is
    exactly this term. ``exact_1000`` has length 1000, so it is not
    truncated, and its last character is *term*. ``longer`` continues
    past that character with another splitter and a different filler, so
    the query is longer than 1000 characters and the term that begins at
    position 1000 is still exactly *term*. The first 999 characters of
    either query end on the splitter and do not contain *term*.
    """
    if len(term) != 1 or not term.isascii() or not term.isalnum():
        raise HarnessError(
            f"boundary term {term!r} must be one ASCII letter or digit"
        )
    filler = "x"
    if term.casefold() == filler:
        raise HarnessError(
            f"boundary term {term!r} collides with the filler letter"
        )
    tail = "z" if term.casefold() != "z" else "y"
    if tail.casefold() == term.casefold() or tail == filler:
        raise HarnessError(
            f"tail filler {tail!r} collides with the boundary term or the pad"
        )
    splitter = " "
    pad = filler * 998
    exact = pad + splitter + term
    if len(exact) != 1000:
        raise HarnessError(f"exact query length is {len(exact)}, not 1000")
    if exact.encode("utf-8") != exact.encode("ascii"):
        raise HarnessError("boundary query is not ASCII")
    if exact[998] != splitter or exact[999] != term:
        raise HarnessError(
            "splitter is not immediately before position 1000, or position "
            f"1000 is not the boundary term: {exact[-2:]!r}"
        )
    if term in exact[:999]:
        raise HarnessError("boundary term appears before position 1000")
    if _alnum_parts(exact) != [pad, term]:
        raise HarnessError(
            "exact query did not split into the filler and the boundary "
            f"term: {_alnum_parts(exact)!r}"
        )
    if _alnum_parts(exact[:999]) != [pad]:
        raise HarnessError(
            "a 999-character window of the exact query still contains the "
            f"boundary term: {_alnum_parts(exact[:999])!r}"
        )
    longer = exact + splitter + (tail * 40)
    if len(longer) <= 1000:
        raise HarnessError(
            f"longer query is only {len(longer)} characters"
        )
    if not longer.startswith(exact):
        raise HarnessError(
            "longer query does not keep the exact 1000-character prefix"
        )
    if longer[999] != term or longer[1000] != splitter:
        raise HarnessError(
            "the term that begins at position 1000 is not one character "
            "bounded by a splitter"
        )
    if term in longer[:999] or term in longer[1000:]:
        raise HarnessError(
            "boundary term also appears outside position 1000, so a "
            "shorter window could still carry it"
        )
    if _alnum_parts(longer[:1000]) != [pad, term]:
        raise HarnessError(
            "the first 1000 characters of the longer query do not keep "
            f"the boundary term: {_alnum_parts(longer[:1000])!r}"
        )
    if _alnum_parts(longer[:999]) != [pad]:
        raise HarnessError(
            "a 999-character window of the longer query still contains "
            f"the boundary term: {_alnum_parts(longer[:999])!r}"
        )
    full_terms = _alnum_parts(longer)
    if len(full_terms) < 2 or full_terms[1] != term:
        raise HarnessError(
            "the full query's term that begins at position 1000 is not "
            f"exactly the boundary term: {full_terms!r}"
        )
    return exact, longer


def field_tokens_do_not_start_with(term: str, *texts: str) -> None:
    """Fixture guard: no field token equals *term* or starts with it.

    A hit on such a token would not be a title match on the concept this
    term names. Raises when the fixture is unusable. Does not call the
    product.
    """
    if not term or not term.isascii() or not term.isalnum():
        raise HarnessError(
            f"term {term!r} is not an ASCII letter-digit token"
        )
    folded = term.casefold()
    for text in texts:
        for part in _alnum_parts(text):
            if part.casefold().startswith(folded):
                raise HarnessError(
                    f"fixture token {part!r} starts with term {term!r}; "
                    "a hit would not be carried by the intended title"
                )


@dataclass(frozen=True)
class DeepDirectoryPrefixProbe:
    """Generated directory ref, a character-sibling ref, and a path under each.

    ``segments_under`` counts slash-separated pieces after the matching
    directory and is at least 2. ``path_under_sibling`` begins with
    ``directory_ref`` and the next character is not a slash, so the shorter
    ref is a character prefix and not a directory boundary.
    """

    directory_ref: str
    sibling_ref: str
    path_under_directory: str
    path_under_sibling: str
    segments_under: int


def _gen_hex(n: int = 6) -> str:
    """Runtime-unique lowercase hex (the suite's own generated sample material)."""
    return uuid.uuid4().hex[:n]


# Generated per test process; the documents carry none of these values.
# A two-level directory, a character-sibling of it that is not a directory
# boundary, a ``.go`` file under each, and a bare ``.go`` file name.
SAMPLE_TOP_DIR = f"p{_gen_hex(6)}"
SAMPLE_PREFIX_DIR = f"{SAMPLE_TOP_DIR}/a{_gen_hex(5)}"
SAMPLE_SIBLING_DIR = f"{SAMPLE_PREFIX_DIR}x{_gen_hex(5)}"
SAMPLE_FILE = f"{SAMPLE_PREFIX_DIR}/l{_gen_hex(5)}.go"
SAMPLE_SIBLING_FILE = f"{SAMPLE_SIBLING_DIR}/x.go"
SAMPLE_BARE_GO = f"f{_gen_hex(6)}.go"
SAMPLE_NESTED_DIR = f"{SAMPLE_TOP_DIR}/m{_gen_hex(5)}"
# A letters-plus-digit keyword term and a two-word title that starts with it.
SAMPLE_TERM = f"Oa{_gen_hex(5)}2"
SAMPLE_TERM_TITLE = f"{SAMPLE_TERM} P{_gen_hex(5)}"
# A title shared by two concepts, its first word, and two identities whose
# ascending order is fixed.
SAMPLE_SHARED_WORD = f"S{_gen_hex(6)}"
SAMPLE_SHARED_TITLE = f"{SAMPLE_SHARED_WORD} t{_gen_hex(5)}"
SAMPLE_LOW_ID = f"a{_gen_hex(6)}"
SAMPLE_HIGH_ID = f"z{_gen_hex(6)}"
# A cap far above the 100 ceiling (never 101).
SAMPLE_BIG_CAP = 1000 + int(_gen_hex(5), 16) % 999000

# The directory-prefix strings the fixed probes use. A generated probe that
# lands on these strings would not show that a generated directory matches.
_PUBLIC_DIRECTORY_PREFIX_SAMPLES = (
    SAMPLE_PREFIX_DIR,
    SAMPLE_SIBLING_DIR,
    SAMPLE_FILE,
    SAMPLE_SIBLING_FILE,
)

# The relative code_ref the filesystem-absolute search plants as a fixed
# probe. A longer absolute caller that stores this string does not show
# that a generated relative ref matches.
_PUBLIC_ABSOLUTE_RELATIVE_REF = SAMPLE_FILE


def _segments_strictly_under(directory: str, path: str) -> list[str]:
    """Slash-separated pieces of *path* after a directory boundary."""
    boundary = directory + "/"
    if not path.startswith(boundary):
        raise HarnessError(
            f"path {path!r} is not under directory {directory!r}"
        )
    parts = path[len(boundary):].split("/")
    if any(part == "" for part in parts):
        raise HarnessError(f"empty path segment in {path!r}")
    if len(parts) < 2:
        raise HarnessError(
            f"path {path!r} has {len(parts)} segment(s) under {directory!r}; "
            "a directory-prefix probe needs two or more"
        )
    return parts


def _build_deep_directory_prefix_probe() -> DeepDirectoryPrefixProbe:
    directory, continuation, mid, nest, leaf, ext = unique_compact(
        "dir", "ctn", "mid", "nst", "lf", "ext"
    )
    if "/" in directory or "/" in continuation or "*" in directory or "*" in continuation:
        raise HarnessError("generated directory pieces contain a slash or a star")
    directory_ref = directory
    sibling_ref = directory + continuation
    filename = f"{leaf}.{ext}"
    tail = f"{mid}/{nest}/{filename}"
    path_under_directory = f"{directory_ref}/{tail}"
    path_under_sibling = f"{sibling_ref}/{tail}"
    under_directory = _segments_strictly_under(directory_ref, path_under_directory)
    under_sibling = _segments_strictly_under(sibling_ref, path_under_sibling)
    if under_directory != under_sibling:
        raise HarnessError(
            "paths under the directory and the character-sibling differ "
            f"below the boundary: {under_directory!r} vs {under_sibling!r}"
        )
    if path_under_sibling.startswith(directory_ref + "/") or path_under_sibling == directory_ref:
        raise HarnessError(
            "sibling path is a directory boundary of the shorter ref"
        )
    if not path_under_sibling.startswith(directory_ref):
        raise HarnessError(
            "sibling path does not share the directory ref's characters"
        )
    if path_under_sibling[len(directory_ref)] == "/":
        raise HarnessError(
            "character after the shorter ref is a slash"
        )
    if path_under_directory.startswith(sibling_ref + "/") or path_under_directory == sibling_ref:
        raise HarnessError(
            "sibling ref is a directory prefix of the nested path"
        )
    for value in (
        directory_ref,
        sibling_ref,
        path_under_directory,
        path_under_sibling,
    ):
        if value in _PUBLIC_DIRECTORY_PREFIX_SAMPLES or SAMPLE_PREFIX_DIR in value:
            raise HarnessError(
                f"generated directory-prefix probe collided with a public "
                f"sample: {value!r}"
            )
    return DeepDirectoryPrefixProbe(
        directory_ref=directory_ref,
        sibling_ref=sibling_ref,
        path_under_directory=path_under_directory,
        path_under_sibling=path_under_sibling,
        segments_under=len(under_directory),
    )


def generated_deep_directory_prefix_probe() -> DeepDirectoryPrefixProbe:
    """Directory ref and character-sibling, each with a path two or more segments under it.

    The directory name is generated. The sibling ref continues that name
    without a slash. Fixture generation that cannot satisfy those
    constraints raises; it does not return a fixed probe.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_deep_directory_prefix_probe()
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build a deep directory-prefix probe: {last_error}"
    )


@dataclass(frozen=True)
class UnsuffixedRecursiveDirectoryProbe:
    """Directory-scoped recursive ref with no filename suffix.

    ``code_ref`` is ``<directory>/**``. ``nested_path`` sits two or more
    segments under that directory, and its final segment has no dot.
    ``outside_path`` repeats that tail under a different directory.
    """

    directory: str
    code_ref: str
    nested_path: str
    outside_path: str


def _build_unsuffixed_recursive_directory_probe() -> UnsuffixedRecursiveDirectoryProbe:
    directory, mid, nest, leaf, outside = unique_compact(
        "urd", "urm", "urn", "url", "uru"
    )
    for piece in (directory, mid, nest, leaf, outside):
        if "/" in piece or "*" in piece or "." in piece:
            raise HarnessError(
                f"generated recursive-directory piece is not a plain name: {piece!r}"
            )
    if (
        directory == outside
        or directory.startswith(outside)
        or outside.startswith(directory)
    ):
        raise HarnessError(
            "scoped directory and outside directory share a prefix"
        )
    code_ref = f"{directory}/**"
    remainder = code_ref.split("**", 1)[1]
    if remainder not in ("",):
        raise HarnessError(
            f"recursive ref still has a filename suffix: {code_ref!r}"
        )
    if "*." in code_ref or code_ref.count("**") != 1:
        raise HarnessError(
            f"recursive ref is not a single unsuffixed **: {code_ref!r}"
        )
    tail = f"{mid}/{nest}/{leaf}"
    nested_path = f"{directory}/{tail}"
    outside_path = f"{outside}/{tail}"
    under = _segments_strictly_under(directory, nested_path)
    if "." in under[-1] or "*" in under[-1]:
        raise HarnessError(
            f"nested filename is not an unsuffixed name: {under[-1]!r}"
        )
    if not outside_path.endswith("/" + tail):
        raise HarnessError("outside path does not share the nested tail")
    if outside_path.startswith(directory + "/") or nested_path.startswith(outside + "/"):
        raise HarnessError("inside and outside paths share a directory boundary")
    return UnsuffixedRecursiveDirectoryProbe(
        directory=directory,
        code_ref=code_ref,
        nested_path=nested_path,
        outside_path=outside_path,
    )


def unsuffixed_recursive_directory_probe() -> UnsuffixedRecursiveDirectoryProbe:
    """Generated ``<dir>/**`` plus a nested unsuffixed file and an outside twin.

    The stored ref has no ``*.<ext>`` suffix. The nested path crosses a
    slash under that directory. Fixture generation that cannot satisfy
    those constraints raises.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_unsuffixed_recursive_directory_probe()
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build an unsuffixed recursive-directory probe: {last_error}"
    )


def one_segment_recursive_suffix_paths(
    leaf: str, ext: str, other: str
) -> tuple[str, str, str]:
    """``**/*.{ext}``, one-segment ``{leaf}.{ext}``, and ``{leaf}.{other}``.

    The hit and the miss keep the same filename stem and differ only in
    the suffix. Neither caller path contains a slash. A recursive suffix
    match that runs only when the path contains a slash cannot hit the
    first path. Pieces that are not plain names, or suffixes that are
    not distinct, raise.
    """
    for label, piece in (("leaf", leaf), ("ext", ext), ("other", other)):
        if not piece or not piece.isalnum():
            raise HarnessError(
                f"one-segment recursive suffix {label} is not alphanumeric: "
                f"{piece!r}"
            )
        if any(mark in piece for mark in "/*?.[]"):
            raise HarnessError(
                f"one-segment recursive suffix {label} contains a path or "
                f"glob marker: {piece!r}"
            )
    if ext == other or ext in other or other in ext:
        raise HarnessError(
            f"one-segment recursive suffixes are not distinct: {ext!r} vs {other!r}"
        )
    code_ref = f"**/*.{ext}"
    hit_path = f"{leaf}.{ext}"
    miss_path = f"{leaf}.{other}"
    if (
        "/" in hit_path
        or "/" in miss_path
        or hit_path.count(".") != 1
        or miss_path.count(".") != 1
    ):
        raise HarnessError(
            "recursive suffix paths are not one segment: "
            f"{hit_path!r} {miss_path!r}"
        )
    if not hit_path.endswith("." + ext) or not miss_path.endswith("." + other):
        raise HarnessError(
            "one-segment paths do not end in the requested suffix"
        )
    if miss_path.endswith("." + ext) or hit_path.endswith("." + other):
        raise HarnessError("one-segment hit and miss share a suffix")
    if (
        not code_ref.startswith("**/")
        or code_ref.count("**") != 1
        or "/" in code_ref[3:]
        or not code_ref.endswith("*." + ext)
    ):
        raise HarnessError(
            f"stored ref is not an unscoped recursive suffix: {code_ref!r}"
        )
    return code_ref, hit_path, miss_path


@dataclass(frozen=True)
class PartialSegmentGlobProbe:
    """Single-segment glob whose star is only part of the filename stem.

    ``pattern`` is ``{prefix}*.{ext}``. ``hit_path`` is ``{prefix}{leaf}.{ext}``
    with no slash, so the star matches ``{leaf}`` inside that one segment.
    ``cross_path`` is ``{prefix}/{leaf}.{ext}``: matching it requires the star
    to consume a slash. ``nested_path`` places ``hit_path`` under another
    directory, so matching the whole path also requires the star to cross a
    slash. ``whole_stem_path`` is a different one-segment file of the same
    suffix that does not start with ``prefix``. ``wrong_suffix_path`` keeps
    the prefixed stem and changes the suffix.
    """

    pattern: str
    hit_path: str
    cross_path: str
    nested_path: str
    whole_stem_path: str
    wrong_suffix_path: str


def _build_partial_segment_glob_probe() -> PartialSegmentGlobProbe:
    prefix, leaf, ext, other, other_ext, directory = unique_compact(
        "gpx", "glf", "gex", "got", "gsx", "gdr"
    )
    for piece in (prefix, leaf, ext, other, other_ext, directory):
        if not piece or not piece.isalnum():
            raise HarnessError(
                f"partial-segment glob piece is not alphanumeric: {piece!r}"
            )
        if any(mark in piece for mark in "/*?[]"):
            raise HarnessError(
                f"partial-segment glob piece contains a glob marker: {piece!r}"
            )
    pattern = f"{prefix}*.{ext}"
    hit_path = f"{prefix}{leaf}.{ext}"
    cross_path = f"{prefix}/{leaf}.{ext}"
    nested_path = f"{directory}/{hit_path}"
    whole_stem_path = f"{other}.{ext}"
    wrong_suffix_path = f"{prefix}{leaf}.{other_ext}"
    segments = pattern.split("/")
    if len(segments) != 1:
        raise HarnessError(f"partial-segment pattern has a slash: {pattern!r}")
    stem, dot, suffix = segments[0].partition(".")
    if (
        dot != "."
        or suffix != ext
        or stem.count("*") != 1
        or pattern.count("*") != 1
    ):
        raise HarnessError(
            f"partial-segment pattern is not prefix*.ext: {pattern!r}"
        )
    star_at = stem.index("*")
    if star_at <= 0 or stem[:star_at] != prefix or not stem.endswith("*"):
        raise HarnessError(
            f"star is not only part of one filename stem: {pattern!r}"
        )
    if "/" in hit_path or not hit_path.endswith(f".{ext}"):
        raise HarnessError(f"hit path is not one prefixed segment: {hit_path!r}")
    if hit_path[: len(prefix)] != prefix or hit_path[len(prefix): -len(ext) - 1] != leaf:
        raise HarnessError(f"hit path does not keep prefix and leaf: {hit_path!r}")
    star_span = cross_path[len(prefix): -len(f".{ext}")]
    if "/" not in star_span or not cross_path.endswith(f".{ext}"):
        raise HarnessError(
            f"cross path does not put a slash in the star span: {cross_path!r}"
        )
    if nested_path.count("/") != 1 or nested_path.rsplit("/", 1)[-1] != hit_path:
        raise HarnessError(
            f"nested path is not the hit filename under one directory: {nested_path!r}"
        )
    if (
        "/" in whole_stem_path
        or whole_stem_path.startswith(prefix)
        or not whole_stem_path.endswith(f".{ext}")
    ):
        raise HarnessError(
            f"whole-stem path is not a different one-segment file of .{ext}: "
            f"{whole_stem_path!r}"
        )
    if (
        "/" in wrong_suffix_path
        or not wrong_suffix_path.startswith(prefix + leaf + ".")
        or wrong_suffix_path.endswith(f".{ext}")
        or f".{ext}" in wrong_suffix_path
    ):
        raise HarnessError(
            f"wrong-suffix path still matches the pattern suffix: {wrong_suffix_path!r}"
        )
    closed_shapes = (
        f"*.{ext}",
        f"{directory}/*.{ext}",
        "*.go",
        f"{directory}/*.go",
    )
    if pattern in closed_shapes or pattern.startswith("*.") or "/**" in pattern:
        raise HarnessError(
            f"partial-segment pattern collapsed into a whole-stem shape: {pattern!r}"
        )
    return PartialSegmentGlobProbe(
        pattern=pattern,
        hit_path=hit_path,
        cross_path=cross_path,
        nested_path=nested_path,
        whole_stem_path=whole_stem_path,
        wrong_suffix_path=wrong_suffix_path,
    )


def partial_segment_glob_probe() -> PartialSegmentGlobProbe:
    """Generated ``{prefix}*.{ext}`` plus a same-segment hit and slash-crossing misses.

    The stored star is not the entire filename stem. Fixture generation that
    cannot satisfy that raises; it does not return ``*.{ext}`` or
    ``{dir}/*.{ext}``.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_partial_segment_glob_probe()
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build a partial-segment glob probe: {last_error}"
    )


@dataclass(frozen=True)
class EarlierSegmentGlobProbe:
    """Single stars that sit in a path segment before the filename.

    ``leading_pattern`` is ``*/{leaf}.{ext}``. ``leading_hit`` is one
    segment plus that literal filename, so the star matches exactly one
    segment. ``leading_cross`` puts another segment in that star's span.
    ``leading_other_leaf`` keeps the one-segment span and changes the
    literal filename.

    ``scoped_pattern`` is ``{dir}/*/{leaf}.{ext}``. ``scoped_hit`` is that
    directory, one middle segment, and the literal filename.
    ``scoped_cross`` puts another segment in the star's span.
    ``scoped_other_leaf`` changes only the filename. ``scoped_other_dir``
    keeps the star's one segment and the filename, and changes the
    literal directory.
    """

    leading_pattern: str
    leading_hit: str
    leading_cross: str
    leading_other_leaf: str
    scoped_pattern: str
    scoped_hit: str
    scoped_cross: str
    scoped_other_leaf: str
    scoped_other_dir: str


def _path_segments(label: str, text: str) -> list[str]:
    parts = text.split("/")
    if not parts or any(part == "" for part in parts):
        raise HarnessError(f"{label} has an empty path segment: {text!r}")
    return parts


def _refuse_path_containment(paths: Sequence[str]) -> None:
    """Raise when one stored path is a directory prefix or slash-suffix of another.

    The product treats a stored ref as a directory prefix of a longer
    path, and a caller path that ends with ``/`` plus a relative ref as
    that ref. Two probe paths that stand in either relation would make
    an exact anchor look like a glob hit.
    """
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left == right:
                raise HarnessError(f"probe paths are not distinct: {left!r}")
            if right.startswith(left + "/") or left.startswith(right + "/"):
                raise HarnessError(
                    f"probe path is a directory prefix of another: {left!r} vs {right!r}"
                )
            if right.endswith("/" + left) or left.endswith("/" + right):
                raise HarnessError(
                    f"probe path is a slash-suffix of another: {left!r} vs {right!r}"
                )


def _build_earlier_segment_glob_probe() -> EarlierSegmentGlobProbe:
    segment, deeper, leaf, ext, other_leaf, directory, middle, extra, scoped_leaf, scoped_ext, scoped_other, other_dir = unique_compact(
        "esg", "esd", "esl", "ese", "eso", "edr", "emd", "eex", "esf", "esx", "est", "eod"
    )
    pieces = (
        segment, deeper, leaf, ext, other_leaf, directory, middle, extra,
        scoped_leaf, scoped_ext, scoped_other, other_dir,
    )
    for piece in pieces:
        if not piece or not piece.isalnum():
            raise HarnessError(
                f"earlier-segment glob piece is not alphanumeric: {piece!r}"
            )
        if any(mark in piece for mark in "*?[]./"):
            raise HarnessError(
                f"earlier-segment glob piece contains a glob or slash mark: {piece!r}"
            )
    leading_filename = f"{leaf}.{ext}"
    scoped_filename = f"{scoped_leaf}.{scoped_ext}"
    leading_pattern = f"*/{leading_filename}"
    leading_hit = f"{segment}/{leading_filename}"
    leading_cross = f"{segment}/{deeper}/{leading_filename}"
    leading_other_leaf = f"{segment}/{other_leaf}.{ext}"
    scoped_pattern = f"{directory}/*/{scoped_filename}"
    scoped_hit = f"{directory}/{middle}/{scoped_filename}"
    scoped_cross = f"{directory}/{middle}/{extra}/{scoped_filename}"
    scoped_other_leaf = f"{directory}/{middle}/{scoped_other}.{scoped_ext}"
    scoped_other_dir = f"{other_dir}/{middle}/{scoped_filename}"
    probe = EarlierSegmentGlobProbe(
        leading_pattern=leading_pattern,
        leading_hit=leading_hit,
        leading_cross=leading_cross,
        leading_other_leaf=leading_other_leaf,
        scoped_pattern=scoped_pattern,
        scoped_hit=scoped_hit,
        scoped_cross=scoped_cross,
        scoped_other_leaf=scoped_other_leaf,
        scoped_other_dir=scoped_other_dir,
    )
    for label, pattern in (
        ("leading", probe.leading_pattern),
        ("scoped", probe.scoped_pattern),
    ):
        if pattern.count("*") != 1 or "**" in pattern:
            raise HarnessError(
                f"{label} pattern is not a single non-recursive star: {pattern!r}"
            )
        segments = _path_segments(label, pattern)
        if "*" in segments[-1]:
            raise HarnessError(
                f"{label} star is still in the filename segment: {pattern!r}"
            )
        if segments.count("*") != 1:
            raise HarnessError(
                f"{label} star is not its own path segment: {pattern!r}"
            )
    leading_parts = _path_segments("leading pattern", probe.leading_pattern)
    if leading_parts != ["*", leading_filename]:
        raise HarnessError(
            f"leading pattern is not */{{leaf}}.{{ext}}: {probe.leading_pattern!r}"
        )
    if _path_segments("leading hit", probe.leading_hit) != [segment, leading_filename]:
        raise HarnessError(
            f"leading hit is not one segment plus the literal filename: {probe.leading_hit!r}"
        )
    if _path_segments("leading cross", probe.leading_cross) != [
        segment, deeper, leading_filename
    ]:
        raise HarnessError(
            f"leading cross does not put a slash in the star span: {probe.leading_cross!r}"
        )
    if _path_segments("leading other leaf", probe.leading_other_leaf) != [
        segment, f"{other_leaf}.{ext}"
    ]:
        raise HarnessError(
            f"leading other leaf changed more than the filename: {probe.leading_other_leaf!r}"
        )
    scoped_parts = _path_segments("scoped pattern", probe.scoped_pattern)
    if scoped_parts != [directory, "*", scoped_filename]:
        raise HarnessError(
            f"scoped pattern is not {{dir}}/*/{{leaf}}.{{ext}}: {probe.scoped_pattern!r}"
        )
    if _path_segments("scoped hit", probe.scoped_hit) != [
        directory, middle, scoped_filename
    ]:
        raise HarnessError(
            f"scoped hit is not the directory, one segment, and the filename: "
            f"{probe.scoped_hit!r}"
        )
    if _path_segments("scoped cross", probe.scoped_cross) != [
        directory, middle, extra, scoped_filename
    ]:
        raise HarnessError(
            f"scoped cross does not put a slash in the star span: {probe.scoped_cross!r}"
        )
    if _path_segments("scoped other leaf", probe.scoped_other_leaf) != [
        directory, middle, f"{scoped_other}.{scoped_ext}"
    ]:
        raise HarnessError(
            f"scoped other leaf changed more than the filename: {probe.scoped_other_leaf!r}"
        )
    if _path_segments("scoped other dir", probe.scoped_other_dir) != [
        other_dir, middle, scoped_filename
    ]:
        raise HarnessError(
            f"scoped other dir changed more than the literal directory: "
            f"{probe.scoped_other_dir!r}"
        )
    closed_shapes = (
        f"*.{ext}",
        f"*.{scoped_ext}",
        f"{directory}/*.{ext}",
        f"{directory}/*.{scoped_ext}",
        f"{segment}*.{ext}",
        "*.go",
        f"{directory}/*.go",
    )
    if probe.leading_pattern in closed_shapes or probe.scoped_pattern in closed_shapes:
        raise HarnessError(
            "earlier-segment pattern collapsed into a filename star: "
            f"leading={probe.leading_pattern!r} scoped={probe.scoped_pattern!r}"
        )
    concrete = (
        probe.leading_hit,
        probe.leading_cross,
        probe.leading_other_leaf,
        probe.scoped_hit,
        probe.scoped_cross,
        probe.scoped_other_leaf,
        probe.scoped_other_dir,
    )
    _refuse_path_containment(concrete)
    return probe


def earlier_segment_glob_probe() -> EarlierSegmentGlobProbe:
    """Generated ``*/{leaf}.{ext}`` and ``{dir}/*/{leaf}.{ext}`` probes.

    Each star sits in a segment before the filename. Fixture generation
    that cannot keep the star out of the filename raises; it does not
    return ``*.{ext}``, ``{dir}/*.{ext}``, or ``{prefix}*.{ext}``.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_earlier_segment_glob_probe()
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build an earlier-segment glob probe: {last_error}"
    )


def require_core_fields(
    record: Any,
    identity: str,
    concept_type: str,
    title: str,
    description: str,
) -> None:
    """``concept_id``, ``type``, ``title``, and ``description`` carry these values."""
    observed = {
        "identity": hit_field(record, "concept_id"),
        "type": hit_field(record, "type"),
        "title": hit_field(record, "title"),
        "description": hit_field(record, "description"),
    }
    expected = {
        "identity": identity,
        "type": concept_type,
        "title": title,
        "description": description,
    }
    print(
        "[F04] core fields "
        + " ".join(f"{label}={observed[label] == expected[label]}" for label in expected),
        flush=True,
    )
    for label, want in expected.items():
        if observed[label] != want:
            raise AssertionError(
                f"structured hit {label} is {observed[label]!r}, not {want!r}; "
                f"record={record!r}"
            )


def hit_field(record: Any, key: str) -> str:
    """A string key every hit object has: concept_id, title, type, description, governance."""
    if not isinstance(record, Mapping):
        raise AssertionError(f"search hit is not a JSON object: {record!r}")
    if key not in record:
        raise AssertionError(f"search hit has no {key!r} key: {record!r}")
    value = record[key]
    if not isinstance(value, str):
        raise AssertionError(
            f"search hit {key!r} is not a string: {value!r}; record={record!r}"
        )
    return value


def hit_list(record: Any, key: str) -> list[str]:
    """An array-of-strings key that is present only when it has members.

    ``code_refs``, ``tags``, ``inbound``, and ``outbound``. An absent key
    is no members.
    """
    if not isinstance(record, Mapping):
        raise AssertionError(f"search hit is not a JSON object: {record!r}")
    if key not in record:
        return []
    value = record[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AssertionError(
            f"search hit {key!r} is not an array of strings: {value!r}; "
            f"record={record!r}"
        )
    return list(value)


def hit_matched_on(record: Any) -> frozenset[str]:
    """The ``matched_on`` tokens of one hit object."""
    if not isinstance(record, Mapping):
        raise AssertionError(f"search hit is not a JSON object: {record!r}")
    if "matched_on" not in record:
        raise AssertionError(f"search hit has no 'matched_on' key: {record!r}")
    value = record["matched_on"]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AssertionError(
            f"search hit 'matched_on' is not an array of strings: {value!r}"
        )
    unknown = sorted(set(value) - HIT_MATCH_TOKENS)
    if unknown:
        raise AssertionError(
            f"search hit 'matched_on' holds tokens outside the six: {unknown!r}"
        )
    return frozenset(value)


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_code_refs_yaml(refs: Sequence[str]) -> str:
    items = ", ".join(_yaml_quote(str(ref)) for ref in refs)
    return f"[{items}]"


def _is_object_array(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, Mapping) for item in value)


def record_has_json_number(obj: Any) -> bool:
    """True when the hit object's ``score`` is a JSON number."""
    if not isinstance(obj, Mapping) or "score" not in obj:
        return False
    score = obj["score"]
    return isinstance(score, (int, float)) and not isinstance(score, bool)


def search_concept_spec(
    identity: str,
    *,
    concept_type: str,
    title: str,
    description: str,
    body: str,
    tags: Sequence[str] | None = None,
    generated: Mapping[str, str] | None = None,
    governance: str | None = None,
    code_refs: Sequence[str] | None = None,
    resource: str | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Concept dict with optional YAML governance, resource, and quoted code_refs."""
    extra_fields: dict[str, str] = dict(extra or {})
    if governance is not None:
        extra_fields["governance"] = governance
    if code_refs is not None:
        extra_fields["code_refs"] = _render_code_refs_yaml(code_refs)
    if resource is not None:
        if "resource" in extra_fields:
            raise HarnessError("resource was set both as resource and in extra")
        if (
            not isinstance(resource, str)
            or not resource.isalnum()
            or resource.casefold() in GOVERNANCE_TOKENS
        ):
            raise HarnessError(
                "resource scalar must be a non-empty alphanumeric token "
                f"and not a governance word: {resource!r}"
            )
        extra_fields["resource"] = resource
    return concept_spec(
        identity,
        concept_type=concept_type,
        title=title,
        description=description,
        body=body,
        tags=tags,
        generated=generated,
        extra=extra_fields or None,
    )


# Concept frontmatter keys the document names. ``type`` is required; the
# others are the recognized fields. ``membundle_version`` is named on the root
# index. A key outside this set is one the document does not name. The set
# only chooses a fixture key.
_NAMED_FRONTMATTER_KEYS = frozenset({
    "type",
    "title",
    "description",
    "tags",
    "generated",
    "verified",
    "status",
    "governance",
    "code_refs",
    "stale_after",
    "sources",
    "resource",
    "membundle_version",
})


def _token_overlaps(left: str, right: str) -> bool:
    if not left or not right:
        return False
    folded_left = left.lower()
    folded_right = right.lower()
    return folded_left in folded_right or folded_right in folded_left


def _build_unknown_frontmatter_scalar(*occupied: str) -> tuple[str, str]:
    key, value = unique_compact("xfk", "xfv")
    named = {item.casefold() for item in _NAMED_FRONTMATTER_KEYS}
    matched = {item.casefold() for item in MATCHED_FIELD_SET}
    for token, label in ((key, "key"), (value, "value")):
        if not token or not token.isalnum():
            raise HarnessError(
                f"unknown frontmatter {label} is not a plain alphanumeric "
                f"scalar: {token!r}"
            )
        folded = token.casefold()
        if folded in named or folded in matched or folded in GOVERNANCE_TOKENS:
            raise HarnessError(
                f"unknown frontmatter {label} collides with a named field, "
                f"a matched-field token, or a governance word: {token!r}"
            )
    if _token_overlaps(key, value):
        raise HarnessError(
            f"unknown frontmatter key and value overlap: {key!r} vs {value!r}"
        )
    for text in occupied:
        if not isinstance(text, str) or not text:
            raise HarnessError(
                "unknown frontmatter overlap check needs a non-empty "
                f"occupied text: {text!r}"
            )
        if _token_overlaps(key, text) or _token_overlaps(value, text):
            raise HarnessError(
                "unknown frontmatter scalar overlaps an occupied fixture "
                f"text: key={key!r} value={value!r} occupied={text!r}"
            )
    return key, value


def unknown_frontmatter_scalar(*occupied: str) -> tuple[str, str]:
    """A frontmatter key the document does not name, and a plain scalar.

    The key is not a named frontmatter field. The value is alphanumeric, so
    it is one YAML scalar and not a matched-field token. Neither string
    contains or sits inside *occupied* (the title query and the concept's
    other texts). Fixture generation raises when it cannot satisfy that.
    Does not call the product.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_unknown_frontmatter_scalar(*occupied)
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build an unknown frontmatter scalar: {last_error}"
    )


def require_planted_unknown_frontmatter(
    path: str | Path, key: str, value: str
) -> None:
    """The concept file the test wrote has *key* as its own frontmatter scalar.

    Reads the file back. A missing file, a missing fence, or a mapping that
    does not carry that top-level scalar raises. Does not call the product.
    """
    if key.casefold() in {item.casefold() for item in _NAMED_FRONTMATTER_KEYS}:
        raise HarnessError(
            f"refusing to treat a named frontmatter field as unknown: {key!r}"
        )
    if not value:
        raise HarnessError("unknown frontmatter scalar needs a non-empty value")
    dest = Path(path)
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read planted concept {dest}: {exc}") from exc
    mapping, _body = split_yaml_frontmatter(text)
    needle = f"{key}: {value}"
    for line in mapping.splitlines():
        if line.startswith((" ", "\t")):
            continue
        if line.strip() == needle:
            print(
                f"[F04] planted unknown frontmatter {key!r} on {dest.name}",
                flush=True,
            )
            return
    raise HarnessError(
        f"planted concept {dest} has no top-level frontmatter scalar "
        f"{needle!r}; mapping={mapping!r}"
    )


def require_planted_resource_is_sole_copy(path: str | Path, term: str) -> None:
    """The concept file keeps *term* only as its top-level resource scalar.

    Fixture check. Does not call the product. A copy in the filename,
    the body, the type, or any other frontmatter line would either score
    the concept or plant the term in type, code_refs, or governance.
    """
    if (
        not isinstance(term, str)
        or not term.isalnum()
        or term.casefold() in GOVERNANCE_TOKENS
    ):
        raise HarnessError(
            "resource-only plant term must be a non-empty alphanumeric "
            f"token and not a governance word: {term!r}"
        )
    dest = Path(path)
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read planted concept {dest}: {exc}") from exc
    mapping, body = split_yaml_frontmatter(text)
    needle = term.lower()
    if needle in dest.name.lower():
        raise HarnessError(
            f"planted identity filename contains the resource term {term!r}: "
            f"{dest.name!r}"
        )
    if needle in body.lower():
        raise HarnessError(
            f"planted body contains the resource term {term!r}: {body!r}"
        )
    resource_lines = [
        line
        for line in mapping.splitlines()
        if not line[:1].isspace()
        and line.split(":", 1)[0].strip().lower() == "resource"
    ]
    if len(resource_lines) != 1:
        raise HarnessError(
            "planted concept does not have exactly one top-level resource "
            f"line: {mapping!r}"
        )
    raw_value = resource_lines[0].split(":", 1)[1].strip().strip("'\"")
    if raw_value != term:
        raise HarnessError(
            f"planted resource {raw_value!r} is not the query term {term!r}"
        )
    for line in mapping.splitlines():
        if line == resource_lines[0]:
            continue
        if needle in line.lower():
            raise HarnessError(
                "planted frontmatter other than resource contains "
                f"{term!r}: {line!r}"
            )
    print(f"[F04] planted resource-only term on {dest.name}", flush=True)


# Recognized frontmatter that keyword scoring does not use. Governance is
# excluded on purpose: this pass does not plant a term there. Type,
# code_refs, and resource stay on their own checks.
_UNSCORED_RECOGNIZED_FIELDS = frozenset({
    "generated",
    "verified",
    "status",
    "stale_after",
    "sources",
})


def _frontmatter_blocks(mapping: str) -> list[tuple[str, list[str]]]:
    """Top-level frontmatter keys and the lines that belong to each one.

    Raises when a line is indented before any key or is not a key line.
    Fixture check. Does not call the product.
    """
    blocks: list[tuple[str, list[str]]] = []
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        blocks.append((current_key, current_lines))
        current_key = None
        current_lines = []

    for line in mapping.splitlines():
        if not line.strip():
            continue
        if line[:1].isspace() or (
            current_key is not None and line.startswith("-")
        ):
            if current_key is None:
                raise HarnessError(
                    f"indented frontmatter line is outside a field: {line!r}"
                )
            current_lines.append(line)
            continue
        flush()
        if ":" not in line:
            raise HarnessError(f"frontmatter line is not a key: {line!r}")
        key, _value = line.split(":", 1)
        current_key = key.strip()
        current_lines = [line]
    flush()
    return blocks


def _yaml_scalar(line: str) -> str:
    return line.split(":", 1)[1].strip().strip("'\"")


def _child_scalar(line: str) -> tuple[str, str]:
    body = line.strip()
    if body.startswith("-"):
        body = body[1:].strip()
    if ":" not in body:
        raise HarnessError(f"frontmatter child line is not a key: {line!r}")
    key, value = body.split(":", 1)
    return key.strip().lower(), value.strip().strip("'\"")


def _flow_scalars(scalar: str) -> dict[str, str]:
    text = scalar.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise HarnessError(
            f"verified plant is not a flow mapping: {scalar!r}"
        )
    inner = text[1:-1].strip()
    if not inner:
        raise HarnessError("verified plant flow mapping is empty")
    found: dict[str, str] = {}
    for part in inner.split(","):
        if ":" not in part:
            raise HarnessError(
                f"verified plant flow item is not a key: {part!r}"
            )
        key, value = part.split(":", 1)
        name = key.strip().lower()
        if name in found:
            raise HarnessError(
                f"verified plant repeats flow key {name!r}: {scalar!r}"
            )
        found[name] = value.strip().strip("'\"")
    return found


def require_planted_recognized_field_is_sole_copy(
    path: str | Path, field: str, term: str
) -> None:
    """The concept file keeps *term* only inside one unscored recognized field.

    *field* is generated, verified, status, stale_after, or sources.
    Fixture check. Does not call the product. A copy in the filename,
    the body, governance, or any other frontmatter block would either
    score the concept or plant the term outside that field. Governance
    is refused: this plant does not put the term there.
    """
    key = field.strip().lower()
    if key == "governance":
        raise HarnessError("refusing to plant a keyword term in governance")
    if key not in _UNSCORED_RECOGNIZED_FIELDS:
        raise HarnessError(
            "sole-copy plant field must be generated, verified, status, "
            f"stale_after, or sources: {field!r}"
        )
    if (
        not isinstance(term, str)
        or not term.isalnum()
        or term.casefold() in GOVERNANCE_TOKENS
    ):
        raise HarnessError(
            "recognized-field plant term must be a non-empty alphanumeric "
            f"token and not a governance word: {term!r}"
        )
    dest = Path(path)
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read planted concept {dest}: {exc}") from exc
    mapping, body = split_yaml_frontmatter(text)
    needle = term.lower()
    if needle in dest.name.lower():
        raise HarnessError(
            f"planted identity filename contains the {key} term {term!r}: "
            f"{dest.name!r}"
        )
    if needle in body.lower():
        raise HarnessError(
            f"planted body contains the {key} term {term!r}: {body!r}"
        )
    blocks = _frontmatter_blocks(mapping)
    matched = [block for block in blocks if block[0].lower() == key]
    if len(matched) != 1:
        raise HarnessError(
            f"planted concept does not have exactly one {key} block: "
            f"{mapping!r}"
        )
    for block_key, lines in blocks:
        folded = block_key.lower()
        if folded == key:
            continue
        if folded in {"governance", "code_refs", "resource"}:
            raise HarnessError(
                f"planted {key} concept also has {folded}; "
                "that field is not part of this plant"
            )
        for line in lines:
            if needle in line.lower():
                raise HarnessError(
                    f"planted frontmatter other than {key} contains "
                    f"{term!r}: {line!r}"
                )
    _lines = matched[0][1]
    if key in {"status", "stale_after"}:
        if len(_lines) != 1 or _yaml_scalar(_lines[0]) != term:
            raise HarnessError(
                f"planted {key} value is not the query term {term!r}: "
                f"{_lines!r}"
            )
    elif key == "generated":
        if _yaml_scalar(_lines[0]) != "":
            raise HarnessError(
                f"planted generated value is not a block: {_lines[0]!r}"
            )
        children = dict(_child_scalar(line) for line in _lines[1:])
        if children != {"by": term, "at": term}:
            raise HarnessError(
                f"planted generated by/at are not the query term {term!r}: "
                f"{children!r}"
            )
    elif key == "verified":
        if len(_lines) != 1:
            raise HarnessError(
                f"planted verified is not one flow line: {_lines!r}"
            )
        flow = _flow_scalars(_yaml_scalar(_lines[0]))
        if flow != {"by": term, "at": term}:
            raise HarnessError(
                f"planted verified by/at are not the query term {term!r}: "
                f"{flow!r}"
            )
    else:
        if _yaml_scalar(_lines[0]) != "":
            raise HarnessError(
                f"planted sources value is not a block: {_lines[0]!r}"
            )
        children = dict(_child_scalar(line) for line in _lines[1:])
        if children != {
            "id": term,
            "resource": term,
            "title": term,
            "author": term,
        }:
            raise HarnessError(
                "planted sources scalars are not the query term "
                f"{term!r}: {children!r}"
            )
    print(f"[F04] planted {key}-only term on {dest.name}", flush=True)


def require_planted_code_refs_is_sole_copy(
    path: str | Path, term: str, ref: str
) -> None:
    """The concept file keeps *term* only inside one planted code_refs value.

    Fixture check. Does not call the product. A copy in the filename,
    the body, the type, or any other frontmatter line would make a
    correct keyword search return the concept. A missing file, a missing
    fence, or a code_refs line that does not carry *ref* raises.
    """
    if (
        not isinstance(term, str)
        or not term.isalnum()
        or term.casefold() in GOVERNANCE_TOKENS
    ):
        raise HarnessError(
            "code_refs-only plant term must be a non-empty alphanumeric "
            f"token and not a governance word: {term!r}"
        )
    if not isinstance(ref, str) or not ref or term not in ref:
        raise HarnessError(
            f"planted code_refs value {ref!r} does not contain the term {term!r}"
        )
    dest = Path(path)
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read planted concept {dest}: {exc}") from exc
    mapping, body = split_yaml_frontmatter(text)
    needle = term.lower()
    if needle in dest.name.lower():
        raise HarnessError(
            f"planted identity filename contains the code_refs term {term!r}: "
            f"{dest.name!r}"
        )
    if needle in body.lower():
        raise HarnessError(
            f"planted body contains the code_refs term {term!r}: {body!r}"
        )
    ref_lines = [
        line
        for line in mapping.splitlines()
        if not line[:1].isspace()
        and line.split(":", 1)[0].strip().lower() == "code_refs"
    ]
    if len(ref_lines) != 1:
        raise HarnessError(
            "planted concept does not have exactly one top-level code_refs "
            f"line: {mapping!r}"
        )
    if ref not in ref_lines[0]:
        raise HarnessError(
            f"planted code_refs line does not carry {ref!r}: {ref_lines[0]!r}"
        )
    for line in mapping.splitlines():
        if line == ref_lines[0]:
            continue
        if needle in line.lower():
            raise HarnessError(
                "planted frontmatter other than code_refs contains "
                f"{term!r}: {line!r}"
            )
    print(f"[F04] planted code_refs-only term on {dest.name}", flush=True)


def write_concepts_later_first(
    ws: Workspace,
    rel: str | Path,
    specs_in_identity_order: Sequence[Mapping[str, Any]],
) -> Path:
    """Write a bundle with later-sorting identities created first."""
    ordered = sorted(
        specs_in_identity_order,
        key=lambda spec: str(spec["identity"]),
        reverse=True,
    )
    return write_bundle(ws, rel, ordered)


def write_equal_score_title_bundle(
    ws: Workspace,
    rel: str | Path,
    term: str,
    identities: Sequence[str],
) -> Path:
    """N concepts sharing title *term*; identities omit *term*; later file first."""
    if not identities:
        raise HarnessError("equal-score bundle needs at least one identity")
    lowered = term.lower()
    for ident in identities:
        if lowered in ident.lower():
            raise HarnessError(
                f"identity {ident!r} contains title term {term!r}"
            )
    typ, desc, body = unique_tokens("etyp", "edsc", "ebod")
    for token in (typ, desc, body):
        if lowered in token.lower():
            raise HarnessError(
                f"filler {token!r} contains title term {term!r}"
            )
    specs = [
        search_concept_spec(
            ident,
            concept_type=typ,
            title=term,
            description=desc,
            body=f"{body}\n",
        )
        for ident in identities
    ]
    root = write_concepts_later_first(ws, rel, specs)
    print(
        f"[F04] equal-score bundle {root} n={len(identities)} term={term!r}",
        flush=True,
    )
    return root


def plant_keyword_score_tie_later_first(
    ws: Workspace,
    rel: str | Path,
    title: str,
    early_id: str,
    late_id: str,
) -> tuple[str, str]:
    """Two title-only keyword hits. Returns the order the files were written.

    Both concepts share *title* and no other field contains that term, so a
    keyword query for *title* scores them together. The later identity is
    written first. That write order is not identity ascending. The returned
    pair is the list passed to the writer, not a second sort.
    """
    if not early_id < late_id:
        raise HarnessError(
            f"keyword score tie needs {early_id!r} to sort before {late_id!r}"
        )
    lowered = title.lower()
    if not lowered:
        raise HarnessError("keyword score tie needs a non-empty title term")
    for ident in (early_id, late_id):
        if lowered in ident.lower():
            raise HarnessError(
                f"identity {ident!r} contains title term {title!r}"
            )
    typ, desc, body = unique_tokens("etyp", "edsc", "ebod")
    for token in (typ, desc, body):
        if lowered in token.lower():
            raise HarnessError(
                f"filler {token!r} contains title term {title!r}"
            )
    write_order = (late_id, early_id)

    def _spec(ident: str) -> dict[str, Any]:
        return search_concept_spec(
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=f"{body}\n",
        )

    root = write_bundle(ws, rel, [_spec(ident) for ident in write_order])
    print(
        f"[F04] keyword score tie {root} write_order={write_order!r} "
        f"title={title!r}",
        flush=True,
    )
    return write_order


def plant_same_governance_path_tie_later_first(
    ws: Workspace,
    rel: str | Path,
    path: str,
    early_id: str,
    late_id: str,
    *,
    governance: str,
) -> tuple[str, str]:
    """Two path-only hits. Same governance, same code_ref, later identity first.

    A path search with no query scores them together: both match the same
    code_ref and neither carries a keyword the caller searched. The returned
    pair is the order the files were written, not a second sort. That order
    is not concept-identity ascending.
    """
    if governance not in GOVERNANCE_TOKENS:
        raise HarnessError(
            f"path score tie governance must be a governance word: {governance!r}"
        )
    if not early_id or not late_id or not (early_id < late_id):
        raise HarnessError(
            "path score tie needs the earlier identity to sort before the "
            f"later one: {early_id!r} {late_id!r}"
        )
    if early_id in late_id or late_id in early_id:
        raise HarnessError(
            f"path score tie identities overlap: {early_id!r} {late_id!r}"
        )
    if (
        not path
        or path in (early_id, late_id)
        or early_id in path
        or late_id in path
    ):
        raise HarnessError(
            f"path score tie path collides with an identity: {path!r} "
            f"{early_id!r} {late_id!r}"
        )
    typ, title, desc, body = unique_tokens("ptyp", "pttl", "pdsc", "pbod")
    for token in (typ, title, desc, body, governance):
        for ident in (early_id, late_id):
            if token in ident or ident in token:
                raise HarnessError(
                    f"path score tie filler {token!r} collides with {ident!r}"
                )
    write_order = (late_id, early_id)
    if list(write_order) == sorted(write_order):
        raise HarnessError(
            "path score tie write order is already identity ascending: "
            f"{write_order!r}"
        )

    def _spec(ident: str) -> dict[str, Any]:
        return search_concept_spec(
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=f"{body}\n",
            governance=governance,
            code_refs=[path],
        )

    root = write_bundle(ws, rel, [_spec(ident) for ident in write_order])
    print(
        f"[F04] path score tie {root} write_order={write_order!r} "
        f"governance={governance!r} path={path!r}",
        flush=True,
    )
    return write_order


def plant_same_governance_path_query_tie_later_first(
    ws: Workspace,
    rel: str | Path,
    path: str,
    early_id: str,
    late_id: str,
    query: str,
    *,
    governance: str,
) -> tuple[str, str]:
    """Two path hits with one query. Same governance, same keyword contribution.

    Both concepts use *query* as their title and share every other scored
    field, so the keyword contribution of that query is the same on both
    and does not rank one ahead of the other. Both code_refs are *path*.
    The later identity is written first. The returned pair is that write
    order, not concept-identity ascending.
    """
    if governance not in GOVERNANCE_TOKENS:
        raise HarnessError(
            "path query tie governance must be a governance word: "
            f"{governance!r}"
        )
    if not isinstance(query, str) or not query.isalnum():
        raise HarnessError(
            "path query tie needs one alphanumeric query term: "
            f"{query!r}"
        )
    folded_query = query.casefold()
    if (
        folded_query in GOVERNANCE_TOKENS
        or folded_query in MATCHED_FIELD_SET
        or folded_query == "code_refs"
    ):
        raise HarnessError(
            "path query tie query collides with a reserved word: "
            f"{query!r}"
        )
    if not early_id or not late_id or not (early_id < late_id):
        raise HarnessError(
            "path query tie needs the earlier identity to sort before the "
            f"later one: {early_id!r} {late_id!r}"
        )
    if early_id in late_id or late_id in early_id:
        raise HarnessError(
            f"path query tie identities overlap: {early_id!r} {late_id!r}"
        )
    if (
        not path
        or path in (early_id, late_id, query)
        or early_id in path
        or late_id in path
        or query in path
    ):
        raise HarnessError(
            "path query tie path collides with an identity or the query: "
            f"{path!r} {early_id!r} {late_id!r} {query!r}"
        )
    for ident in (early_id, late_id):
        if _token_overlaps(query, ident):
            raise HarnessError(
                "path query tie query overlaps an identity, so the keyword "
                f"contribution would differ: {query!r} {ident!r}"
            )
    typ, desc, body = unique_tokens("qtyp", "qdsc", "qbod")
    for token in (typ, desc, body, governance):
        for ident in (early_id, late_id):
            if _token_overlaps(token, ident):
                raise HarnessError(
                    f"path query tie filler {token!r} collides with {ident!r}"
                )
        if _token_overlaps(token, query):
            raise HarnessError(
                "path query tie filler overlaps the query, so the keyword "
                f"contribution would not be title-only: {token!r} {query!r}"
            )
    write_order = (late_id, early_id)
    if list(write_order) == sorted(write_order):
        raise HarnessError(
            "path query tie write order is already identity ascending: "
            f"{write_order!r}"
        )
    shared_body = f"{body}\n"

    def _spec(ident: str) -> dict[str, Any]:
        return search_concept_spec(
            ident,
            concept_type=typ,
            title=query,
            description=desc,
            body=shared_body,
            governance=governance,
            code_refs=[path],
        )

    root = write_bundle(ws, rel, [_spec(ident) for ident in write_order])
    print(
        f"[F04] path query tie {root} write_order={write_order!r} "
        f"governance={governance!r} path={path!r} query={query!r}",
        flush=True,
    )
    return write_order


def other_non_markdown_filename(stem: str) -> str:
    """A non-Markdown filename other than the planted ``notes.txt``.

    *stem* is one generated path segment. The result does not end in
    ``.md``, does not begin with a dot, and is not ``notes.txt``. Those
    names are load rules already planted elsewhere. A stem that cannot
    form such a name raises instead of returning a substitute.
    """
    if not isinstance(stem, str) or not stem or stem in {".", ".."}:
        raise HarnessError(
            f"non-markdown filename stem must be one path segment: {stem!r}"
        )
    if stem.startswith(".") or "/" in stem or "\\" in stem or ".." in Path(stem).parts:
        raise HarnessError(
            "non-markdown filename stem is not one in-bundle segment: "
            f"{stem!r}"
        )
    name = f"{stem}.json"
    if (
        name == "notes.txt"
        or name.startswith(".")
        or name.endswith(".md")
        or name == "node_modules"
    ):
        raise HarnessError(
            "refusing a non-markdown filename that is already a planted "
            f"load rule: {name!r}"
        )
    return name


def plant_markdown_file(
    root: Path,
    relative: str,
    text: str,
    *,
    distinctive: str,
) -> Path:
    """Write *text* at a bundle-relative path and require *distinctive* on disk.

    Parent directories are created. A path that leaves the bundle, an empty
    distinctive token, or a file that does not contain that token after the
    write raises. The returned path is the file that was read back; a failed
    read is not reported as a missing token.
    """
    if not distinctive:
        raise HarnessError(
            "plant_markdown_file requires a non-empty distinctive token"
        )
    rel = Path(relative)
    if not relative or rel.is_absolute() or ".." in rel.parts:
        raise HarnessError(f"refusing to plant escaping path {relative!r}")
    base = Path(root)
    dest = base / rel
    try:
        dest.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise HarnessError(
            f"planted path escapes bundle: {relative!r}"
        ) from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    written = dest.read_text(encoding="utf-8")
    if distinctive not in written:
        raise HarnessError(
            f"planted file {relative!r} does not contain distinctive token "
            f"{distinctive!r}"
        )
    print(
        f"[F04] planted {relative} bytes={len(written)} "
        f"distinctive={distinctive!r}",
        flush=True,
    )
    return dest


def plant_escaping_directory_symlink(
    bundle_root: Path,
    link_name: str,
    concept_filename: str,
    markdown: str,
    *,
    distinctive: str,
    outside_dir: Path,
) -> Path:
    """Point one in-bundle directory symlink at a directory outside the bundle.

    The outside directory holds *concept_filename*, and that file contains
    *distinctive*. *link_name* is a single directory segment, not a markdown
    filename. The symlink is read back: its resolved target must be that
    outside directory, and that directory must sit outside the bundle. A
    plant that does not leave the bundle, or a file that does not contain
    the token, raises. The returned path is the symlink.
    """
    if not distinctive:
        raise HarnessError(
            "plant_escaping_directory_symlink requires a non-empty distinctive token"
        )
    if distinctive not in markdown:
        raise HarnessError(
            "directory-symlink concept markdown does not contain the "
            f"distinctive token {distinctive!r}"
        )
    link = Path(link_name)
    concept = Path(concept_filename)
    if (
        not link_name
        or link.is_absolute()
        or link.name != link_name
        or link_name.startswith(".")
        or link_name.endswith(".md")
        or link_name == "node_modules"
    ):
        raise HarnessError(
            "directory symlink name must be one segment inside the bundle, "
            f"not a markdown file or a skipped directory: {link_name!r}"
        )
    if (
        not concept_filename
        or concept.is_absolute()
        or concept.name != concept_filename
        or not concept_filename.endswith(".md")
        or concept_filename.startswith(".")
    ):
        raise HarnessError(
            "outside concept must be one markdown filename: "
            f"{concept_filename!r}"
        )
    bundle = Path(bundle_root)
    outside = Path(outside_dir)
    try:
        outside.resolve().relative_to(bundle.resolve())
    except ValueError:
        pass
    else:
        raise HarnessError(
            f"outside directory {outside} is inside the bundle {bundle}"
        )
    outside.mkdir(parents=True, exist_ok=False)
    concept_path = outside / concept
    concept_path.write_text(markdown, encoding="utf-8")
    written = concept_path.read_text(encoding="utf-8")
    if distinctive not in written:
        raise HarnessError(
            f"outside concept {concept_path} does not contain distinctive "
            f"token {distinctive!r}"
        )
    link_path = bundle / link
    if link_path.exists() or link_path.is_symlink():
        raise HarnessError(f"refusing to replace existing path {link_path}")
    os.symlink(outside.resolve(), link_path)
    if not link_path.is_symlink():
        raise HarnessError(f"{link_path} is not a symlink after planting")
    try:
        resolved = link_path.resolve()
    except OSError as exc:
        raise HarnessError(
            f"could not resolve directory symlink {link_path}: {exc}"
        ) from exc
    if not resolved.is_dir():
        raise HarnessError(
            f"directory symlink {link_path} did not resolve to a directory: "
            f"{resolved}"
        )
    if resolved != outside.resolve():
        raise HarnessError(
            f"directory symlink {link_path} resolved to {resolved}, "
            f"not the outside directory {outside.resolve()}"
        )
    try:
        resolved.relative_to(bundle.resolve())
    except ValueError:
        pass
    else:
        raise HarnessError(
            f"directory symlink {link_path} resolved inside the bundle: "
            f"{resolved}"
        )
    held = (resolved / concept).read_text(encoding="utf-8")
    if distinctive not in held:
        raise HarnessError(
            f"resolved directory {resolved} does not hold the concept token "
            f"{distinctive!r}"
        )
    print(
        f"[F04] planted directory symlink {link_name} -> {resolved} "
        f"concept={concept_filename} distinctive={distinctive!r}",
        flush=True,
    )
    return link_path


def plant_escaping_markdown_symlink(
    bundle_root: Path,
    link_name: str,
    markdown: str,
    *,
    distinctive: str,
    outside_file: Path,
) -> Path:
    """Point one in-bundle markdown symlink at a file outside the bundle.

    The outside file contains *distinctive*. *link_name* is a single
    markdown filename inside the bundle. The symlink is read back: its
    resolved target must be that outside file, and that file must sit
    outside the bundle. A plant that does not leave the bundle, or a file
    that does not contain the token, raises. The returned path is the
    symlink.
    """
    if not distinctive:
        raise HarnessError(
            "plant_escaping_markdown_symlink requires a non-empty distinctive token"
        )
    if distinctive not in markdown:
        raise HarnessError(
            "markdown-symlink concept does not contain the distinctive token "
            f"{distinctive!r}"
        )
    link = Path(link_name)
    if (
        not link_name
        or link.is_absolute()
        or link.name != link_name
        or not link_name.endswith(".md")
        or link_name.startswith(".")
        or link_name == "node_modules"
    ):
        raise HarnessError(
            "markdown symlink name must be one .md filename inside the bundle: "
            f"{link_name!r}"
        )
    bundle = Path(bundle_root)
    outside = Path(outside_file)
    if outside.is_dir():
        raise HarnessError(
            f"outside markdown target {outside} is a directory, not a file"
        )
    try:
        outside.resolve().relative_to(bundle.resolve())
    except ValueError:
        pass
    else:
        raise HarnessError(
            f"outside markdown file {outside} is inside the bundle {bundle}"
        )
    outside.parent.mkdir(parents=True, exist_ok=True)
    if outside.exists() or outside.is_symlink():
        raise HarnessError(f"refusing to replace existing outside file {outside}")
    outside.write_text(markdown, encoding="utf-8")
    written = outside.read_text(encoding="utf-8")
    if distinctive not in written:
        raise HarnessError(
            f"outside markdown {outside} does not contain distinctive token "
            f"{distinctive!r}"
        )
    link_path = bundle / link
    if link_path.exists() or link_path.is_symlink():
        raise HarnessError(f"refusing to replace existing path {link_path}")
    os.symlink(outside.resolve(), link_path)
    if not link_path.is_symlink():
        raise HarnessError(f"{link_path} is not a symlink after planting")
    try:
        resolved = link_path.resolve()
    except OSError as exc:
        raise HarnessError(
            f"could not resolve markdown symlink {link_path}: {exc}"
        ) from exc
    if not resolved.is_file():
        raise HarnessError(
            f"markdown symlink {link_path} did not resolve to a file: {resolved}"
        )
    if resolved != outside.resolve():
        raise HarnessError(
            f"markdown symlink {link_path} resolved to {resolved}, "
            f"not the outside file {outside.resolve()}"
        )
    try:
        resolved.relative_to(bundle.resolve())
    except ValueError:
        pass
    else:
        raise HarnessError(
            f"markdown symlink {link_path} resolved inside the bundle: {resolved}"
        )
    held = resolved.read_text(encoding="utf-8")
    if distinctive not in held:
        raise HarnessError(
            f"resolved markdown {resolved} does not contain distinctive token "
            f"{distinctive!r}"
        )
    via_link = link_path.read_text(encoding="utf-8")
    if distinctive not in via_link:
        raise HarnessError(
            f"reading symlink {link_path} did not yield distinctive token "
            f"{distinctive!r}"
        )
    print(
        f"[F04] planted markdown symlink {link_name} -> {resolved} "
        f"distinctive={distinctive!r}",
        flush=True,
    )
    return link_path


def run_search(
    ws: Workspace,
    query: str | None = None,
    bundle: str | Path | None = None,
    *,
    for_path: str | None = None,
    limit: int | None = None,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle search`` with optional query, bundle, path, cap, and JSON."""
    args: list[str] = ["search"]
    if query is not None:
        args.append(str(query))
    elif bundle is not None:
        # The bundle is the documented second positional; an empty query keeps it there.
        args.append("")
    if bundle is not None:
        args.append(str(bundle))
    if for_path is not None:
        args.extend(["--for-path", str(for_path)])
    if limit is not None:
        # Single argv token so a negative cap is not split off as a flag.
        args.append(f"--limit={limit}")
    if structured:
        args.append("--json")
    args.extend(str(item) for item in extra_args)
    print(
        f"[F04] search argv={args!r} cwd={cwd!r} structured={structured}",
        flush=True,
    )
    binary = resolve_search_binary()
    try:
        return ws.invoke(
            args, env_updates=env_updates, cwd=cwd, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_search_binary_missing(binary, exc)


def require_call_leaves_bundle_bytes_unchanged(
    root: str | Path,
    call: Callable[[], Any],
    *,
    label: str,
) -> Any:
    """Read bundle bytes immediately before *call* and immediately after it.

    *call* is the only work between those two reads, so a later call cannot
    put the bytes back before this comparison. A difference fails *label*
    on its own. A snapshot that cannot be read raises; it is not reported
    as an unchanged bundle.
    """
    if not label:
        raise HarnessError("bundle-byte comparison label is empty")
    before = snapshot_tree(root)
    result = call()
    after = snapshot_tree(root)
    print(
        f"[F04] bundle-byte cell {label!r} files={len(before)}",
        flush=True,
    )
    assert before == after, (
        f"{label} mutated bundle bytes; "
        f"before={sorted(before)} after={sorted(after)}"
    )
    return result


def require_search_success(result: RunResult) -> str:
    """Human success carrier: status 0 and standard output in the human form.

    Returns standard output. It is either the hit blocks or the one
    zero-hit line; anything else fails here.
    """
    report = result.stdout_text
    print(
        f"[F04] search-success exit={result.returncode} report_len={len(report)}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"search did not end successfully (exit {result.returncode}); "
            f"report={combined_report(result)!r}"
        )
    human_search_hits(report)
    return report


def require_search_load_failure(result: RunResult) -> str:
    """Load failure: status 2 and a standard-error line ``Error loading bundle: ``."""
    report = combined_report(result)
    print(
        f"[F04] search-load-failure exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode == LOAD_FAILURE_STATUS, (
        f"search of a bundle that cannot be loaded ended with status "
        f"{result.returncode}, not {LOAD_FAILURE_STATUS}; report={report!r}"
    )
    assert _has_line_beginning(result.stderr_text, LOAD_FAILURE_PREFIX), (
        "search of a bundle that cannot be loaded has no standard-error line "
        f"beginning {LOAD_FAILURE_PREFIX!r}; stderr={result.stderr_text!r}"
    )
    return report


def _has_line_beginning(text: str, prefix: str) -> bool:
    return any(line.startswith(prefix) for line in text.split("\n"))


def require_search_failure(result: RunResult) -> str:
    """Failure carrier: process status is not success."""
    report = combined_report(result)
    print(
        f"[F04] search-failure exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode != 0, (
        f"search ended successfully when it must not; report={report!r}"
    )
    return report


def structured_hit_records(
    parsed: Any, *, nil_slice_is_empty: bool = False
) -> list[Any]:
    """A parsed JSON array of hit objects, in rank order.

    Zero hits is an empty array. JSON null is zero hits only on the
    command line, which passes ``nil_slice_is_empty``; from the search
    tool it is not a hit list. Anything else raises.
    """
    if parsed is None:
        if nil_slice_is_empty:
            return []
        raise AssertionError(
            "JSON null is not an empty hit list; zero hits is an empty list"
        )
    if isinstance(parsed, list):
        if _is_object_array(parsed):
            return list(parsed)
        raise HarnessError(
            "structured search output is a list that is not a list of "
            f"objects: {parsed!r}"
        )
    raise HarnessError(
        "structured search output is not a JSON array of hit objects "
        f"(type={type(parsed).__name__}): {parsed!r}"
    )


def require_search_structured_success(result: RunResult) -> list[Any]:
    """Structured success: POSIX success plus a classified hit list."""
    report = combined_report(result)
    print(
        f"[F04] search-structured exit={result.returncode} "
        f"stdout_len={len(result.stdout)}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"structured search did not end successfully "
            f"(exit {result.returncode}); report={report!r}"
        )
    parsed = json_stdout(result)
    # The search command marshals a nil slice as JSON null. That is this
    # command's structured rendering of no hits. The search tool does not
    # use this allowance.
    records = structured_hit_records(parsed, nil_slice_is_empty=True)
    print(f"[F04] structured hits={len(records)}", flush=True)
    return records


def hit_identities(
    records: Sequence[Any],
    expected_identities: Sequence[str],
) -> list[str]:
    """Ordered ``concept_id`` values; each is one of the expected, once."""
    expected = list(expected_identities)
    if not expected:
        raise HarnessError("hit_identities requires at least one expected identity")
    ordered: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        ident = hit_field(record, "concept_id")
        if ident not in expected:
            raise AssertionError(
                f"hit record {index} is {ident!r}, not one of the "
                f"expected identities {expected!r}"
            )
        if ident in seen:
            raise AssertionError(
                f"identity {ident!r} appears in more than one hit record"
            )
        seen.add(ident)
        ordered.append(ident)
    return ordered


@dataclass(frozen=True)
class HumanHit:
    """One human hit block: its first line, description line, and Matches line."""

    rank: int
    governance: str
    score: str
    named: str
    description: str
    matches: tuple[str, ...]

    def names(self, identity: str) -> bool:
        """True when the first line ends ``<identity> (<type>)``."""
        return self.named.startswith(f"{identity} (") and self.named.endswith(")")


def human_search_hits(report: str) -> list[HumanHit]:
    """Hit blocks of human ``search`` standard output, in rank order.

    With hits: a first line, an empty line, then per hit the line
    ``<rank>. [<governance>] [<score>] <identity> (<type>)``, a line of
    four spaces and the description, a line of four spaces, ``Matches: ``
    and the matched-field tokens joined by ``, ``, and an empty line.
    With zero hits: exactly one non-empty line that is not a hit-block
    first line, which is an empty list. Any other text fails.
    """
    if not isinstance(report, str):
        raise HarnessError("human search report is not text")
    lines = report.split("\n")
    if _is_zero_hit_report(lines):
        return []
    if len(lines) < 2 or lines[0] == "" or lines[1] != "":
        raise AssertionError(
            "human search output is neither hit blocks after a first line "
            f"and an empty line, nor the zero-hit line; report={report!r}"
        )
    hits: list[HumanHit] = []
    at = 2
    while at < len(lines) and lines[at] != "":
        block = lines[at : at + 4]
        head = _HUMAN_HIT_LINE.match(block[0])
        if head is None:
            raise AssertionError(
                "human hit line is not "
                "'<rank>. [<governance>] [<score>] <identity> (<type>)': "
                f"{block[0]!r}; report={report!r}"
            )
        if len(block) < 4 or block[3] != "":
            raise AssertionError(
                "human hit block is not three lines followed by an empty "
                f"line: {block!r}; report={report!r}"
            )
        rank = int(head.group(1))
        if rank != len(hits) + 1:
            raise AssertionError(
                f"human hit rank {rank} is not the 1-based position "
                f"{len(hits) + 1}; report={report!r}"
            )
        named = head.group(4)
        if " (" not in named or not named.endswith(")"):
            raise AssertionError(
                f"human hit line does not end '<identity> (<type>)': {block[0]!r}"
            )
        if not block[1].startswith(_HUMAN_INDENT):
            raise AssertionError(
                f"human hit description line does not begin with four spaces: "
                f"{block[1]!r}; report={report!r}"
            )
        if not block[2].startswith(_HUMAN_MATCHES):
            raise AssertionError(
                f"human hit has no '    Matches: ' line: {block[2]!r}; "
                f"report={report!r}"
            )
        listed = block[2][len(_HUMAN_MATCHES) :]
        matches = tuple(listed.split(", ")) if listed else ()
        unknown = sorted(set(matches) - HIT_MATCH_TOKENS)
        if unknown:
            raise AssertionError(
                f"human Matches line holds tokens outside the six: {unknown!r}; "
                f"line={block[2]!r}"
            )
        hits.append(
            HumanHit(
                rank=rank,
                governance=head.group(2),
                score=head.group(3),
                named=named,
                description=block[1][len(_HUMAN_INDENT) :],
                matches=matches,
            )
        )
        at += 4
    if not hits:
        raise AssertionError(
            f"human search output has no hit block; report={report!r}"
        )
    if any(line != "" for line in lines[at:]):
        raise AssertionError(
            f"human search output has text after its hit blocks: {lines[at:]!r}"
        )
    return hits


def human_hit_for(report: str, identity: str) -> HumanHit:
    """The one human hit block whose first line names *identity*."""
    if not identity:
        raise HarnessError("human hit lookup needs an identity")
    found = [hit for hit in human_search_hits(report) if hit.names(identity)]
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one human hit for {identity!r}, found "
            f"{len(found)}; report={report!r}"
        )
    return found[0]


def human_names_identity(report: str, identity: str) -> bool:
    """True when some human hit block names *identity*."""
    return any(hit.names(identity) for hit in human_search_hits(report))


def require_human_identity_absent(report: str, identity: str) -> None:
    """No human hit block names *identity*."""
    if not identity:
        raise HarnessError("human identity absence needs an identity")
    assert not human_names_identity(report, identity), (
        f"human report presents {identity!r} as a hit; report={report!r}"
    )


def human_hit_order(report: str, identities: Sequence[str]) -> list[str]:
    """Order of *identities* over the human hit blocks."""
    return _human_badge_span_identity_order(report, identities)


def _identities_do_not_overlap(identities: Sequence[str]) -> None:
    """Absence of one identity is unreadable when it sits inside another."""
    items = list(identities)
    for index, left in enumerate(items):
        if not left:
            raise HarnessError("human identity check needs a non-empty identity")
        for right in items[index + 1 :]:
            if left in right or right in left:
                raise HarnessError(
                    f"identities overlap, so a human cap is not observable: "
                    f"{left!r} vs {right!r}"
                )


def require_human_identity_prefix(
    report: str,
    kept: Sequence[str],
    withheld: Sequence[str],
) -> list[str]:
    """Human hit blocks name *kept*, in that order, and none of *withheld*.

    The report is the search command when structured output was not
    requested. Order is the order of the hit blocks. A withheld identity
    named by a block means the cap did not apply.
    """
    kept_list = list(kept)
    withheld_list = list(withheld)
    if len(kept_list) < 2:
        raise HarnessError(
            "human identity prefix needs at least two identities, "
            f"got {kept_list!r}"
        )
    if not withheld_list:
        raise HarnessError(
            "human identity prefix needs at least one withheld identity"
        )
    _identities_do_not_overlap(kept_list + withheld_list)
    ordered = concept_identity_order(report, kept_list, form="human")
    assert ordered == kept_list, (
        f"human hit order {ordered!r} != ranked prefix {kept_list!r}"
    )
    for ident in withheld_list:
        assert not human_names_identity(report, ident), (
            f"human report presents {ident!r} beyond the requested cap; "
            f"report={report!r}"
        )
    print(
        f"[F04] human hit prefix={ordered!r} withheld={len(withheld_list)}",
        flush=True,
    )
    return ordered


def require_human_identity_present(report: str, identity: str) -> None:
    """A human hit block names *identity*.

    Used as the live baseline that more hits than the cap are presented
    when that cap is not requested.
    """
    if not identity:
        raise HarnessError("human identity presence needs an identity")
    assert human_names_identity(report, identity), (
        f"human report does not present identity {identity!r}: {report!r}"
    )
    print(f"[F04] human presents {identity!r}", flush=True)


def require_human_ranked_prefix(
    report: str,
    kept: Sequence[str],
    withheld: Sequence[str],
) -> list[str]:
    """Human hit blocks name *kept*, in that order, and none of *withheld*.

    A later identity that is also named means the cap did not apply. An
    identity that no block names is not a shorter legal prefix.
    """
    kept_list = list(kept)
    withheld_list = list(withheld)
    if len(kept_list) < 2:
        raise HarnessError(
            "human ranked prefix needs at least two identities, "
            f"got {kept_list!r}"
        )
    if not withheld_list:
        raise HarnessError("human ranked prefix needs at least one withheld identity")
    _identities_do_not_overlap(kept_list + withheld_list)
    ordered = concept_identity_order(report, kept_list, form="human")
    assert ordered == kept_list, (
        f"human hit order {ordered!r} != ranked prefix {kept_list!r}"
    )
    for ident in withheld_list:
        assert not human_names_identity(report, ident), (
            f"human report presents {ident!r} beyond the cap"
        )
    print(
        f"[F04] human ranked prefix={len(ordered)} withheld={len(withheld_list)}",
        flush=True,
    )
    return ordered


def matched_field_tokens(
    record: Any,
    stripped_texts: Sequence[str],
) -> frozenset[str]:
    """Keyword members of the hit's ``matched_on`` tokens.

    Keeping only title, tags, description, id, and body is the
    observation, not a verdict. *stripped_texts* is unused: the tokens
    are read from ``matched_on``.
    """
    remaining = frozenset(hit_matched_on(record) & MATCHED_FIELD_SET)
    print(f"[F04] matched-field tokens={sorted(remaining)}", flush=True)
    return remaining


def assert_matched_keyword_fields(
    record: Any,
    stripped_texts: Sequence[str],
    expected: Sequence[str],
) -> frozenset[str]:
    """Keyword matched-field tokens are exactly *expected*, no other member.

    *expected* is a subset of title, tags, description, id, and body.
    A title-only hit that also names tags fails. A hit that matched two
    of those fields and names only one of them fails the same way.
    A name outside that set in *expected* is a harness error.
    """
    expected_set = frozenset(expected)
    unknown = expected_set - MATCHED_FIELD_SET
    if unknown:
        raise HarnessError(
            f"expected matched fields are outside the keyword set: "
            f"{sorted(unknown)!r}"
        )
    tokens = matched_field_tokens(record, stripped_texts)
    if tokens != expected_set:
        raise AssertionError(
            f"matched keyword fields {sorted(tokens)!r} "
            f"are not exactly {sorted(expected_set)!r}"
        )
    return tokens


def code_ref_match_reported(record: Any, stripped_texts: Sequence[str]) -> bool:
    """True when the hit's ``matched_on`` tokens include ``code_refs``."""
    reported = CODE_REF_MATCH_CHANNEL in hit_matched_on(record)
    print(f"[F04] code-ref channel present={reported}", flush=True)
    return reported


def assert_path_hit_reports(
    record: Any,
    stripped_texts: Sequence[str],
    keyword_fields: Sequence[str],
) -> frozenset[str]:
    """A path hit names code_refs and exactly the keyword members that matched.

    *keyword_fields* is empty when no member of title, tags, description,
    id, and body matched. A member that matched and is absent fails. A
    member of that set that did not match and is present fails. A path
    hit that does not name code_refs fails the same way.
    """
    tokens = assert_matched_keyword_fields(record, stripped_texts, keyword_fields)
    if not code_ref_match_reported(record, stripped_texts):
        raise AssertionError(
            "path hit does not report a code_refs match after the path and "
            "the concept's own texts are stripped; keyword fields "
            f"{sorted(tokens)!r}; record={record!r}"
        )
    return tokens


def assert_human_path_hit_reports(
    report: str,
    identity: str,
    keyword_fields: Sequence[str],
    *,
    cohort: Sequence[str],
    strip_texts: Sequence[str],
) -> frozenset[str]:
    """A human path hit names code_refs and exactly the keyword fields that matched.

    The hit is the block whose first line names *identity*; its
    ``Matches:`` line lists the tokens. *keyword_fields* is empty when no
    keyword member matched. A member that matched and is absent fails. A
    member that did not match and is present fails. A path hit that does
    not list code_refs fails the same way.
    """
    expected = frozenset(keyword_fields)
    unknown = expected - MATCHED_FIELD_SET
    if unknown:
        raise HarnessError(
            "expected human keyword fields are outside the keyword set: "
            f"{sorted(unknown)!r}"
        )
    if identity not in list(cohort):
        raise HarnessError(
            f"path-hit identity {identity!r} is not in the cohort {list(cohort)!r}"
        )
    hit = human_hit_for(report, identity)
    found = frozenset(hit.matches)
    keywords = found - {CODE_REF_MATCH_CHANNEL}
    print(
        f"[F04] human path hit {identity!r} names={sorted(found)}",
        flush=True,
    )
    if CODE_REF_MATCH_CHANNEL not in found:
        raise AssertionError(
            "human path hit does not name code_refs; "
            f"identity={identity!r} matches={hit.matches!r}"
        )
    if keywords != expected:
        raise AssertionError(
            f"human path hit keyword fields {sorted(keywords)!r} "
            f"are not exactly {sorted(expected)!r}; "
            f"identity={identity!r} matches={hit.matches!r}"
        )
    return keywords


def assert_single_effective_governance(
    record: Any,
    expected: str,
    strip_tokens: Sequence[str],
) -> None:
    """The hit's ``governance`` is *expected*."""
    if expected not in GOVERNANCE_TOKENS:
        raise HarnessError(f"expected governance is not one of the three words: {expected!r}")
    found = hit_field(record, "governance")
    print(f"[F04] effective governance value={found!r} expected={expected!r}", flush=True)
    assert found == expected, (
        f"structured hit governance is {found!r}, not the effective "
        f"governance {expected!r}"
    )


def assert_lowercase_effective_governance(
    record: Any,
    expected: str,
    strip_tokens: Sequence[str],
) -> None:
    """The hit's ``governance`` is the lowercase word *expected*.

    Declared values are compared case-insensitively and the effective
    value is the lowercase word. ``HOLD`` or ``Hold`` in that key fails,
    and so does a different governance word.
    """
    if expected not in GOVERNANCE_TOKENS:
        raise HarnessError(
            f"expected governance is not one of the three words: {expected!r}"
        )
    found = hit_field(record, "governance")
    print(
        f"[F04] lowercase effective governance value={found!r} "
        f"expected={expected!r}",
        flush=True,
    )
    assert found == expected, (
        f"structured hit governance is {found!r}, not the lowercase "
        f"effective governance {expected!r}"
    )


def assert_folded_declared_governance(
    record: Any,
    declared: str,
    strip_tokens: Sequence[str],
) -> None:
    """Effective governance is the lowercase form of a mixed declared spelling.

    *declared* is the spelling stored in the file. It must be constraint,
    hold, or context in a capitalization that is not already the lowercase
    word. The structured hit must carry that lowercase word. The file
    spelling may remain beside it. A hit whose only governance word is
    *declared* fails. A hit that carries a different governance word,
    including the default for an omitted value, fails.
    """
    if not isinstance(declared, str) or not declared:
        raise HarnessError(
            f"declared governance spelling is missing: {declared!r}"
        )
    effective = declared.lower()
    if effective not in GOVERNANCE_TOKENS:
        raise HarnessError(
            "declared governance is not one of the three words: "
            f"{declared!r}"
        )
    if declared == effective:
        raise HarnessError(
            "declared spelling is already the lowercase word, so echoing "
            f"the file is the same observation as the fold: {declared!r}"
        )
    assert_lowercase_effective_governance(record, effective, strip_tokens)


def require_zero_hits_success(
    result: RunResult,
    *,
    structured: bool,
    live_identities: Sequence[str] = (),
) -> str:
    """Zero-hit success: an empty hit list, or the human zero-hit line.

    Structured: status 0 and ``[]`` or ``null`` on standard output. Human:
    status 0 and standard output is the one zero-hit line (exactly one
    non-empty line, not a hit-block line). Returns standard output.
    """
    if structured:
        records = require_search_structured_success(result)
        if records:
            raise AssertionError(
                f"zero-hit structured search returned {len(records)} hits: "
                f"{records!r}"
            )
        report = result.stdout_text
    else:
        report = require_search_success(result)
        require_human_zero_hit_line(report)
    print(
        f"[F04] zero-hit success structured={structured} "
        f"identities={list(live_identities)!r} report_len={len(report)}",
        flush=True,
    )
    return report


def require_human_zero_hit_line(report: str) -> str:
    """*report* is the one zero-hit line: exactly one non-empty line that is
    not a hit-block first line (Contract Output forms, ``search`` human)."""
    if not isinstance(report, str):
        raise HarnessError("human zero-hit report is not text")
    lines = report.split("\n")
    assert _is_zero_hit_report(lines), (
        "human zero-hit output is not exactly one non-empty line that is "
        f"not a hit block; report={report!r}"
    )
    return lines[0]


def assert_human_zero_hit_miss_statement(
    zero_report: str,
    live_hit_report: str,
    path_tokens: Sequence[str],
    fixture_tokens: Sequence[str],
    live_identities: Sequence[str] = (),
) -> tuple[str, str]:
    """Human zero-hit output is the zero-hit line; the live report has hit blocks.

    *zero_report* is the one zero-hit line. *live_hit_report* is the contrast on the same bundle and
    holds at least one hit block. The wording of the zero-hit line is not read.
    """
    line = require_human_zero_hit_line(zero_report)
    live_hits = human_search_hits(live_hit_report)
    print(
        f"[F04] human zero-hit line={line!r} live hits={len(live_hits)}",
        flush=True,
    )
    assert live_hits, (
        "the live-hit contrast is itself a zero-hit report; "
        f"report={live_hit_report!r}"
    )
    return line, live_hit_report


def require_unmatched_path_filter_is_miss(
    ws: Workspace,
    query: str,
    bundle: str,
    for_path: str,
    identity: str,
    fixture_tokens: Sequence[str],
    *,
    badge: str,
) -> None:
    """Supplied path matches no code reference; keywords would still hit.

    The same query with no path is the live keyword hit and must present
    *identity* after *badge*. With the path, human output (structured
    output not requested) succeeds, states that nothing matched, and does
    not present *identity*. The search tool returns an empty hit list,
    not that keyword hit. JSON null is not the tool's empty list. The
    structured command-line list is observed separately.
    """
    if not query or not for_path or not identity or not bundle:
        raise HarnessError(
            "unmatched path filter needs a query, a bundle, a path, and "
            "an identity"
        )
    if badge not in GOVERNANCE_TOKENS:
        raise HarnessError(f"badge is not a governance word: {badge!r}")
    human_live = require_search_success(run_search(ws, query, bundle))
    assert_human_concept_identity_after_badge(
        human_live, badge, identity, query=query
    )
    human_miss = require_zero_hits_success(
        run_search(ws, query, bundle, for_path=for_path),
        structured=False,
        live_identities=[identity],
    )
    assert_human_zero_hit_miss_statement(
        human_miss,
        human_live,
        path_tokens_for_search(bundle, ws.path, for_path),
        fixture_tokens,
        live_identities=[identity],
    )
    tool_live = require_mcp_search_success(
        mcp_search(ws, query=query, bundle=bundle)
    )
    assert identity_in_records(tool_live, identity), (
        "keyword search without the path did not return the concept on "
        f"the search tool: {tool_live!r}"
    )
    tool_miss = require_mcp_search_success(
        mcp_search(ws, query=query, for_path=for_path, bundle=bundle)
    )
    assert tool_miss == [], (
        "a path that matches no code reference returned hits on the "
        f"search tool, including a keyword hit: {tool_miss!r}"
    )


def require_search_usage_failure(
    result: RunResult,
    zero_hit_report: str,
    load_error_report: str,
    path_tokens: Sequence[str],
    fixture_tokens: Sequence[str] = (),
) -> str:
    """Neither-query-nor-path: status 1 and usage text carrying ``Usage:``.

    The zero-hit contrast is the zero-hit line and the missing-bundle
    contrast carries a line beginning ``Error loading bundle: ``; the
    usage run is neither: its status is 1, not 0 and not 2.
    """
    report = combined_report(result)
    print(
        f"[F04] usage-failure exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode == USAGE_FAILURE_STATUS, (
        "search with neither query nor path ended with status "
        f"{result.returncode}, not {USAGE_FAILURE_STATUS}; report={report!r}"
    )
    assert USAGE_LITERAL in report, (
        "search with neither query nor path printed no usage text "
        f"carrying {USAGE_LITERAL!r}; report={report!r}"
    )
    require_human_zero_hit_line(zero_hit_report)
    assert _has_line_beginning(load_error_report, LOAD_FAILURE_PREFIX), (
        "missing-bundle contrast has no line beginning "
        f"{LOAD_FAILURE_PREFIX!r}; report={load_error_report!r}"
    )
    return report


def require_search_load_error(
    result: RunResult,
    usage_report: str,
    path_tokens: Sequence[str],
    fixture_tokens: Sequence[str] = (),
    zero_hit_report: str | None = None,
) -> str:
    """Load error: status 2 and a standard-error ``Error loading bundle: `` line.

    The usage contrast carries ``Usage:`` and the zero-hit contrast is
    the zero-hit line.
    """
    report = require_search_load_failure(result)
    assert USAGE_LITERAL in usage_report, (
        f"usage contrast carries no {USAGE_LITERAL!r}; report={usage_report!r}"
    )
    if zero_hit_report is not None:
        require_human_zero_hit_line(zero_hit_report)
    return report


def _tool_first_text(reply: Mapping[str, Any]) -> str:
    """Text of the first content item of a tools/call result."""
    result = reply.get("result")
    if not isinstance(result, Mapping):
        raise AssertionError(f"tools/call reply has no result object: {reply!r}")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise AssertionError(f"tool result has no content items: {result!r}")
    first = content[0]
    if not isinstance(first, Mapping) or not isinstance(first.get("text"), str):
        raise AssertionError(
            f"tool result's first content item has no text: {first!r}"
        )
    return first["text"]


def mcp_membundle_search(
    ws: Workspace,
    arguments: Mapping[str, Any],
    *,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
) -> McpSearchOutcome:
    """One ``membundle_search`` tools/call. A missing reply for *request_id* raises."""
    lines = [
        rpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "f04-suite", "version": "0"},
            },
            id=1,
        ),
        rpc_request(
            "tools/call",
            {"name": "membundle_search", "arguments": dict(arguments)},
            id=request_id,
        ),
    ]
    print(
        f"[F04] mcp membundle_search arguments={dict(arguments)!r} id={request_id!r}",
        flush=True,
    )
    binary = resolve_search_binary()
    try:
        batch = ws.mcp_batch(lines, cwd=cwd, binary=binary)
    except FileNotFoundError as exc:
        _raise_if_search_binary_missing(binary, exc)
    reply = mcp_reply_for_id(batch, request_id)
    if mcp_is_protocol_error(reply):
        payload, report_text = None, str(reply.get("error"))
    else:
        report_text = _tool_first_text(reply)
        try:
            payload = json.loads(report_text)
        except json.JSONDecodeError:
            payload = None
    print(
        f"[F04] mcp reply protocol_error={mcp_is_protocol_error(reply)} "
        f"tool_error={mcp_is_tool_error(reply)} text={report_text!r}",
        flush=True,
    )
    return McpSearchOutcome(
        batch=batch, reply=reply, payload=payload, report_text=report_text
    )


def mcp_search(
    ws: Workspace,
    query: str | None = None,
    for_path: str | None = None,
    bundle: str | Path | None = None,
    limit: int | None = None,
    *,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
) -> McpSearchOutcome:
    """membundle_search with optional query, path, bundle, and cap."""
    arguments: dict[str, Any] = {}
    if query is not None:
        arguments["query"] = query
    if for_path is not None:
        arguments["for_path"] = for_path
    if bundle is not None:
        arguments["bundle"] = str(bundle)
    if limit is not None:
        arguments["limit"] = limit
    return mcp_membundle_search(ws, arguments, request_id=request_id, cwd=cwd)


def require_mcp_search_success(outcome: McpSearchOutcome) -> list[Any]:
    """MCP success: not a tool/protocol error; the result text is a JSON hit array.

    JSON null is not an empty list. A character-cut miss, a fifty-term
    miss, and the neither-query-nor-path tool call all use this rule.
    """
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            f"membundle_search returned a protocol error instead of a hit list: "
            f"{outcome.reply!r}"
        )
    if mcp_is_tool_error(outcome.reply):
        raise AssertionError(
            f"membundle_search marked a tool error on a successful search: "
            f"{outcome.report_text!r}"
        )
    text = _tool_first_text(outcome.reply)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"membundle_search result text is not JSON ({exc}): {text!r}"
        ) from exc
    records = structured_hit_records(parsed)
    print(f"[F04] mcp hits={len(records)}", flush=True)
    return records


def require_mcp_empty_success(outcome: McpSearchOutcome) -> list[Any]:
    """MCP success with an empty hit list (not a tool error)."""
    records = require_mcp_search_success(outcome)
    if records:
        raise AssertionError(
            f"membundle_search neither-query-nor-path returned hits: {records!r}"
        )
    return records


def require_mcp_search_load_failure(outcome: McpSearchOutcome) -> str:
    """A bundle that cannot be loaded is a tool-level failure with the stated text.

    The result has ``isError`` true and the text of its first content
    item begins ``Failed to load bundle from ``. Any successful tools/call
    is not that failure: a hit list, an empty list, and JSON null are all
    success.
    """
    tool = mcp_is_tool_error(outcome.reply)
    print(
        f"[F04] mcp load-failure protocol_error="
        f"{mcp_is_protocol_error(outcome.reply)} tool_error={tool}",
        flush=True,
    )
    assert tool, (
        "membundle_search of a bundle that cannot be loaded is not a "
        "tool-level failure (isError true); "
        f"reply={outcome.reply!r}"
    )
    text = _tool_first_text(outcome.reply)
    assert text.startswith(TOOL_LOAD_FAILURE_PREFIX), (
        "membundle_search load failure text does not begin "
        f"{TOOL_LOAD_FAILURE_PREFIX!r}: {text!r}"
    )
    return text


def require_search_entry_load_refusal(
    ws: Workspace,
    entry: str,
    bundle: str,
    outside_title: str,
) -> None:
    """One public search entry must fail the load of *bundle*.

    *entry* is ``command`` (``membundle search``) or ``tool`` (``membundle_search``).
    Returning *outside_title* as a hit is success, not a load refusal: that
    outcome fails here. A zero-hit success also fails here. The command's
    carrier is the load-failure class: status 2 and a standard-error line
    beginning ``Error loading bundle: ``. The tool's carrier is a
    tool-level failure whose text begins ``Failed to load bundle from ``.
    """
    if entry not in ("command", "tool"):
        raise HarnessError(
            f"search load refusal entry must be command or tool, got {entry!r}"
        )
    if not bundle or not outside_title:
        raise HarnessError(
            "search load refusal needs a bundle and the outside concept title"
        )
    if entry == "command":
        result = run_search(ws, outside_title, bundle, structured=True)
        require_search_load_failure(result)
        print(
            f"[F04] command load refusal bundle={bundle!r} title={outside_title!r}",
            flush=True,
        )
        return
    outcome = mcp_search(ws, query=outside_title, bundle=bundle)
    require_mcp_search_load_failure(outcome)
    print(
        f"[F04] tool load refusal bundle={bundle!r} title={outside_title!r}",
        flush=True,
    )


def _search_public_entry_records(
    ws: Workspace,
    entry: str,
    bundle: str,
    query: str,
) -> list[Any]:
    """Hit list from one public search entry. A non-success load raises.

    *entry* is ``command`` (``membundle search``) or ``tool`` (``membundle_search``).
    Success is a classified hit list. A non-success process status, a
    tool error, and a protocol error are not that list.
    """
    if entry == "command":
        return require_search_structured_success(
            run_search(ws, query, bundle, structured=True)
        )
    if entry == "tool":
        return require_mcp_search_success(
            mcp_search(ws, query=query, bundle=bundle)
        )
    raise HarnessError(
        f"search entry must be command or tool, got {entry!r}"
    )


def _assert_no_hit_carries(
    records: Sequence[Any],
    markers: Sequence[str],
    *,
    label: str,
) -> None:
    """No hit's identity, type, title, or description is one of *markers*."""
    expected = list(markers)
    if not expected:
        raise HarnessError(f"{label} needs at least one outside marker")
    for marker in expected:
        if not marker:
            raise HarnessError(f"{label} has an empty outside marker")
    for index, record in enumerate(records):
        values = [
            hit_field(record, key)
            for key in ("concept_id", "type", "title", "description")
        ]
        found = [marker for marker in expected if marker in values]
        assert not found, (
            f"{label} returned the outside concept on hit {index}; "
            f"markers={found!r} values={values!r}"
        )


def require_escaping_directory_symlink_not_walked(
    ws: Workspace,
    entry: str,
) -> None:
    """An escaping directory symlink is not walked; search still succeeds.

    The bundle holds one concept the query matches, and another concept
    that exists only through a directory symlink whose resolved target
    leaves the bundle and that the same query matches when that file is
    a real path. Search succeeds, the in-bundle concept is a hit, and
    the outside concept is not. A non-success load fails. A hit that
    carries the outside concept fails. A Markdown-file symlink is a
    different outcome and is not planted here.
    """
    if entry not in ("command", "tool"):
        raise HarnessError(
            f"directory-symlink search entry must be command or tool, got {entry!r}"
        )
    (
        link_name,
        stem,
        inside_id,
        shared_title,
        inside_type,
        outside_type,
        inside_desc,
        outside_desc,
        inside_body,
        outside_body,
    ) = unique_tokens(
        "dir", "stem", "inn", "ttl", "ity", "oty", "idc", "odc", "ibd", "obd"
    )
    outside_identity = f"{link_name}/{stem}"
    concept_filename = f"{stem}.md"
    outside_markers = (outside_identity, outside_type, outside_desc)
    for marker in outside_markers:
        for owned in (inside_id, inside_type, shared_title, inside_desc, inside_body):
            if marker == owned or marker in owned or owned in marker:
                raise HarnessError(
                    "outside marker overlaps an in-bundle field, so absence "
                    f"is not readable: {marker!r} vs {owned!r}"
                )
    outside_markdown = render_concept_markdown(
        concept_type=outside_type,
        title=shared_title,
        description=outside_desc,
        body=f"{outside_body}\n",
    )
    rel_real = unique_tokens("kbreal")[0]
    rel_link = unique_tokens("kblink")[0]
    real_root = write_bundle(ws, rel_real, [])
    plant_markdown_file(
        real_root,
        f"{link_name}/{concept_filename}",
        outside_markdown,
        distinctive=outside_desc,
    )
    real_hits = _search_public_entry_records(ws, entry, rel_real, shared_title)
    assert identity_in_records(real_hits, outside_identity), (
        "the same query did not hit the outside concept when that file "
        "is a real path, so a miss through the symlink would not show "
        f"that the symlink was skipped; identity={outside_identity!r} "
        f"hits={real_hits!r}"
    )
    require_core_fields(
        record_for_identity(real_hits, outside_identity),
        outside_identity,
        outside_type,
        shared_title,
        outside_desc,
    )
    link_root = write_bundle(
        ws,
        rel_link,
        [
            search_concept_spec(
                inside_id,
                concept_type=inside_type,
                title=shared_title,
                description=inside_desc,
                body=f"{inside_body}\n",
            )
        ],
    )
    plant_escaping_directory_symlink(
        link_root,
        link_name,
        concept_filename,
        outside_markdown,
        distinctive=outside_desc,
        outside_dir=ws.path / unique_tokens("outside")[0],
    )
    link_hits = _search_public_entry_records(ws, entry, rel_link, shared_title)
    assert identity_in_records(link_hits, inside_id), (
        "search succeeded without the in-bundle concept; an escaping "
        "directory symlink is not a load error, and that concept must "
        f"be a hit; identity={inside_id!r} hits={link_hits!r}"
    )
    require_core_fields(
        record_for_identity(link_hits, inside_id),
        inside_id,
        inside_type,
        shared_title,
        inside_desc,
    )
    _assert_no_hit_carries(
        link_hits,
        outside_markers,
        label=f"{entry} search through an escaping directory symlink",
    )
    print(
        f"[F04] {entry} left the escaping directory symlink unwalked; "
        f"inside={inside_id!r} outside={outside_identity!r}",
        flush=True,
    )


def identity_in_records(records: Sequence[Any], identity: str) -> bool:
    """True when some hit's ``concept_id`` is *identity*."""
    return any(hit_field(record, "concept_id") == identity for record in records)


def require_search_tool_title_hit(
    ws: Workspace,
    bundle: str,
    title: str,
    identity: str,
) -> list[Any]:
    """A title search on membundle_search returns the concept with *identity*.

    Success is a hit list that is not a tool error. The identity is an
    exact string value on one hit. An empty list, a protocol error, and
    a hit list that does not carry that identity all fail.
    """
    if not bundle or not title or not identity:
        raise HarnessError(
            "search-tool title hit needs a bundle, a title, and an identity"
        )
    records = require_mcp_search_success(
        mcp_search(ws, query=title, bundle=bundle)
    )
    assert identity_in_records(records, identity), (
        "membundle_search title search did not return the concept; "
        f"title={title!r} identity={identity!r} hits={records!r}"
    )
    return records


def require_search_tool_title_omitted(
    ws: Workspace,
    bundle: str,
    title: str,
) -> list[Any]:
    """A title search on membundle_search is a successful empty hit list.

    The title lives only in a file a loaded bundle does not index. Zero
    hits on the tool is an empty list, not a tool error and not JSON
    null. Any hit means that file was indexed, or the tool dumped the
    bundle. A failure to classify the payload raises; it is not an empty
    list.
    """
    if not bundle or not title:
        raise HarnessError(
            "search-tool title omission needs a bundle and a title"
        )
    records = require_mcp_search_success(
        mcp_search(ws, query=title, bundle=bundle)
    )
    assert records == [], (
        "membundle_search indexed a document a loaded bundle omits; "
        f"title={title!r} hits={records!r}"
    )
    return records


def require_identity_order(
    records: Sequence[Any],
    expected: Sequence[str],
) -> list[str]:
    """Hit-list array order equals *expected* (ranking carrier)."""
    assert len(records) == len(expected), (
        f"hit count {len(records)} != {len(expected)}; expected={list(expected)!r}"
    )
    ordered = hit_identities(records, expected)
    print(f"[F04] identity order={ordered!r}", flush=True)
    assert ordered == list(expected), (
        f"hit-list order {ordered!r} != expected {list(expected)!r}"
    )
    return ordered


def _human_badge_span_identity_order(
    report: str,
    identities: Sequence[str],
) -> list[str]:
    """Which of *identities* the successive human hit blocks name, in order.

    A block that names none of *identities* is not a position. An
    identity named by two blocks fails.
    """
    expected = list(identities)
    if len(expected) < 2:
        raise HarnessError(
            "human identity order needs at least two identities, "
            f"got {expected!r}"
        )
    if len(set(expected)) != len(expected):
        raise HarnessError(f"matching identities are not unique: {expected!r}")
    _identities_do_not_overlap(expected)
    ordered: list[str] = []
    for hit in human_search_hits(report):
        found = [ident for ident in expected if hit.names(ident)]
        if not found:
            continue
        if len(found) != 1:
            raise AssertionError(
                "human hit line does not name one concept; "
                f"found={found!r} line={hit.named!r}"
            )
        if found[0] in ordered:
            raise AssertionError(
                f"identity {found[0]!r} is named by more than one human hit"
            )
        ordered.append(found[0])
    return ordered


def concept_identity_order(
    observation: str | Sequence[Any],
    matching_identities: Sequence[str],
    *,
    form: str,
) -> list[str]:
    """Concept-identity order for one output form.

    Structured form, including both tool hit lists, is the sequence of
    hit records. Human form, keyword and path, is the sequence of concept
    identities inside successive governance-badge spans. Mentions outside
    those spans are not positions.
    """
    if form == "structured":
        if isinstance(observation, str):
            raise HarnessError(
                "structured identity order needs hit records, not report text"
            )
        return hit_identities(observation, matching_identities)
    if form == "human":
        if not isinstance(observation, str):
            raise HarnessError(
                "human identity order needs the human report text"
            )
        return _human_badge_span_identity_order(observation, matching_identities)
    raise HarnessError(
        f"identity order form must be 'structured' or 'human', got {form!r}"
    )


def require_repeated_search_identity_order(
    first_records: Sequence[Any],
    second_records: Sequence[Any],
    matching_identities: Sequence[str],
) -> list[str]:
    """Two identical searches list the same identities in the same order.

    *matching_identities* is the match set for this query, not a rank.
    Either call may already be in the order a one-call check would accept.
    The two calls still have to agree. A later call that permutes that
    order fails here. Structured form walks the hit records.
    """
    matching = list(matching_identities)
    if len(matching) < 2:
        raise HarnessError(
            "repeated-search order needs at least two matching identities, "
            f"got {matching!r}"
        )
    if len(set(matching)) != len(matching):
        raise HarnessError(f"matching identities are not unique: {matching!r}")
    first = concept_identity_order(first_records, matching, form="structured")
    second = concept_identity_order(second_records, matching, form="structured")
    print(
        f"[F04] repeated identity orders first={first!r} second={second!r}",
        flush=True,
    )
    if set(first) != set(matching):
        raise AssertionError(
            "first search did not return exactly the matching identities; "
            f"order={first!r} matching={matching!r}"
        )
    if set(second) != set(matching):
        raise AssertionError(
            "second identical search did not return exactly the matching "
            f"identities; order={second!r} matching={matching!r}"
        )
    if first != second:
        raise AssertionError(
            "identical searches returned different identity orders; "
            f"first={first!r} second={second!r}"
        )
    return first


def require_repeated_human_search_identity_order(
    first_report: str,
    second_report: str,
    matching_identities: Sequence[str],
) -> list[str]:
    """Two identical human searches list the same badge-span identity order.

    Order is the concept identities inside successive governance-badge
    spans, not the first time each identity appears anywhere in the
    report. Keyword and path share this reader. *matching_identities* is
    the match set, not a required rank. Either call may already be in the
    order a one-call check would accept. The two calls still have to
    agree on the span order. A later call that permutes the badge-prefixed
    hits fails here even when a leading listing of the identities stays
    fixed. An identity that appears only outside the spans is not a
    position. An empty report, or a report that omits one of the
    identities from those spans, is not an order.
    """
    matching = list(matching_identities)
    if len(matching) < 2:
        raise HarnessError(
            "repeated human search order needs at least two matching "
            f"identities, got {matching!r}"
        )
    if len(set(matching)) != len(matching):
        raise HarnessError(f"matching identities are not unique: {matching!r}")
    _identities_do_not_overlap(matching)
    first = concept_identity_order(first_report, matching, form="human")
    second = concept_identity_order(second_report, matching, form="human")
    print(
        f"[F04] repeated human identity orders first={first!r} "
        f"second={second!r}",
        flush=True,
    )
    if set(first) != set(matching) or set(second) != set(matching):
        raise AssertionError(
            "identical human searches did not each present the matching "
            f"identities; first={first!r} second={second!r} "
            f"matching={matching!r}"
        )
    if first != second:
        raise AssertionError(
            "identical human searches returned different identity orders; "
            f"first={first!r} second={second!r}"
        )
    return first


def require_cap_above_100_returns_at_most_100(
    records: Sequence[Any],
    ranked_prefix: Sequence[str],
    *,
    requested_cap: int,
    planted: int,
    surface: str,
) -> list[str]:
    """A requested cap above 100, other than the fixed large cap, returns at most 100.

    *ranked_prefix* is the first 100 identities in the order a cap of 100
    returns on the same hits. *planted* must be greater than 100 so an
    implementation that returns every hit fails. *requested_cap* must be
    an integer above 100 and must not be ``SAMPLE_BIG_CAP``; that cap is a
    separate ceiling check.
    """
    if isinstance(requested_cap, bool) or not isinstance(requested_cap, int):
        raise HarnessError(
            f"{surface} requested cap must be an int, got {requested_cap!r}"
        )
    if requested_cap <= 100 or requested_cap == SAMPLE_BIG_CAP:
        raise HarnessError(
            f"{surface} above-ceiling probe requested cap {requested_cap}; "
            f"need an integer above 100 other than {SAMPLE_BIG_CAP}"
        )
    if not isinstance(planted, int) or isinstance(planted, bool) or planted <= 100:
        raise HarnessError(
            f"{surface} above-ceiling probe planted {planted!r} hits; "
            "need more than 100"
        )
    prefix = list(ranked_prefix)
    if len(prefix) != 100:
        raise HarnessError(
            f"{surface} ranked prefix has {len(prefix)} identities; "
            "the ceiling comparison needs the first 100"
        )
    if planted <= len(prefix):
        raise HarnessError(
            f"{surface} planted {planted} hits, which is not more than the "
            f"{len(prefix)}-identity ceiling prefix"
        )
    assert len(records) <= 100, (
        f"{surface} cap {requested_cap} returned {len(records)} of {planted} "
        "hits; a requested cap above 100 returns at most 100"
    )
    return require_identity_order(records, prefix)


def record_for_identity(records: Sequence[Any], identity: str) -> Any:
    """The unique hit object whose ``concept_id`` is *identity*."""
    matches = [
        record
        for record in records
        if hit_field(record, "concept_id") == identity
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one hit for {identity!r}, found {len(matches)}"
        )
    return matches[0]


def assert_identifiable_human_hits(
    report: str,
    hits: Sequence[tuple[str, Sequence[str]]],
) -> None:
    """Each human hit block carries its identity and its governance badge.

    Each item is ``(lowercase governance badge, identifying strings)``;
    the first string is the concept identity. The blocks that name those
    identities come in the order given, and each block's badge is the
    lowercase word constraint, hold, or context given for it. A
    different spelling of that word is not that badge.
    """
    if not hits:
        raise HarnessError("identifiable-hit check needs at least one hit")
    wanted: list[tuple[str, str]] = []
    for badge, identifiers in hits:
        if badge not in GOVERNANCE_TOKENS:
            raise HarnessError(f"badge is not a governance word: {badge!r}")
        own = [item for item in identifiers if item]
        if not own:
            raise HarnessError(f"hit {badge!r} has no identifying strings")
        wanted.append((badge, own[0]))
    identities = [ident for _badge, ident in wanted]
    blocks = human_search_hits(report)
    ordered: list[str] = []
    for block in blocks:
        ordered.extend(ident for ident in identities if block.names(ident))
    print(f"[F04] human hits named={ordered!r} wanted={identities!r}", flush=True)
    assert ordered == identities, (
        f"human hit blocks name {ordered!r}, not {identities!r} in that "
        f"order; report={report!r}"
    )
    for badge, ident in wanted:
        block = human_hit_for(report, ident)
        assert block.governance == badge, (
            f"human hit {ident!r} carries governance badge "
            f"{block.governance!r}, not {badge!r}; report={report!r}"
        )


def assert_human_concept_identity_after_badge(
    report: str,
    badge: str,
    identity: str,
    *,
    query: str,
) -> None:
    """The concept identity sits in the span after this hit's governance badge.

    The query that was just sent already contains the term that matched.
    Echoing that query after the badge, or printing the description alone,
    does not identify the concept. *identity* is the concept identity, and
    it must not occur in *query*. Punctuation around the badge stays the
    implementer's. A structured record is still not this human hit.
    """
    if not isinstance(identity, str) or not identity.strip():
        raise HarnessError(
            "concept identity after the badge needs a non-empty identity"
        )
    if not isinstance(query, str) or query == "":
        raise HarnessError(
            "concept-identity human check needs the query that was sent"
        )
    if badge not in GOVERNANCE_TOKENS:
        raise HarnessError(f"badge is not a governance word: {badge!r}")
    if identity in query:
        raise HarnessError(
            f"concept identity {identity!r} is inside the query, so echoing "
            "the query would carry it"
        )
    assert_identifiable_human_hits(report, [(badge, (identity,))])


def require_human_ranked_hits(
    report: str,
    ranked: Sequence[tuple[str, Sequence[str]]],
    *,
    planted_order: Sequence[str],
) -> None:
    """Human hits follow *ranked* order, not the order the files were written.

    Each item is ``(lowercase governance badge, identifying strings)``.
    The first string is that concept's identity. At least one of a hit's
    own strings must sit in that hit: after its badge and before the next
    hit's badge. Pass only strings that belong to that concept. A title
    or description shared with the other hit, or a query term that also
    occurs in the other concept's body, does not show which hit was
    printed. *planted_order* is the order the concept files were written.
    It must be the same identities in a different order, so a printer
    that emits human hits in write order fails.
    """
    if len(ranked) < 2:
        raise HarnessError("human rank check needs at least two hits")
    identities: list[str] = []
    hits: list[tuple[str, tuple[str, ...]]] = []
    for badge, tokens in ranked:
        own = tuple(token for token in tokens if token)
        if len(own) < 1:
            raise HarnessError(
                f"human rank hit {badge!r} has no identifying strings"
            )
        identities.append(own[0])
        hits.append((badge, own))
    planted = list(planted_order)
    if len(planted) != len(identities) or set(planted) != set(identities):
        raise HarnessError(
            "planted write order must name each ranked identity once: "
            f"planted={planted!r} ranked={identities!r}"
        )
    if planted == identities:
        raise HarnessError(
            "planted write order matches the required human rank; "
            "a write-order printer would pass: "
            f"{planted!r}"
        )
    _identities_do_not_overlap(
        [token for _badge, own in hits for token in own]
    )
    assert_identifiable_human_hits(report, hits)
    print(
        f"[F04] human ranked={identities!r} planted={planted!r}",
        flush=True,
    )


def _order_disagrees_with_sort(required: Sequence[str]) -> None:
    ascending = sorted(required)
    descending = list(reversed(ascending))
    if list(required) == ascending or list(required) == descending:
        raise HarnessError(
            "required order agrees with identity sort "
            f"required={list(required)!r} ascending={ascending!r}"
        )


def inverted_governance_identities() -> tuple[str, str, str]:
    """(hold, constraint, context) whose identity sort is not that order.

    Ascending is hold, context, constraint. Descending and later-identity-first
    creation order are constraint, context, hold. Neither is hold, then
    constraint, then context.
    """
    hold_tok, con_tok, ctx_tok = unique_compact("hld", "con", "ctx")
    hold_id = f"ahold{hold_tok}"
    ctx_id = f"mctx{ctx_tok}"
    con_id = f"zcon{con_tok}"
    required = (hold_id, con_id, ctx_id)
    _order_disagrees_with_sort(required)
    if not (hold_id < ctx_id < con_id):
        raise HarnessError(
            f"governance identities did not land in the planned sort: "
            f"{hold_id!r} {ctx_id!r} {con_id!r}"
        )
    return hold_id, con_id, ctx_id


def inverted_convention_identities() -> tuple[str, str, str]:
    """(hold, convention/constraint, other-omit context) not in identity sort.

    Ascending is hold, context, convention/. Descending and later-first
    creation order are convention/, context, hold. Required rank is hold,
    then the convention/ omit (constraint), then the other omit (context).
    """
    hold_tok, con_tok, ctx_tok = unique_compact("hld", "cvn", "ctx")
    hold_id = f"ahold{hold_tok}"
    ctx_id = f"bctx{ctx_tok}"
    con_id = f"convention/{con_tok}"
    required = (hold_id, con_id, ctx_id)
    _order_disagrees_with_sort(required)
    if not (hold_id < ctx_id < con_id):
        raise HarnessError(
            f"convention identities did not land in the planned sort: "
            f"{hold_id!r} {ctx_id!r} {con_id!r}"
        )
    if ctx_id.startswith("convention/"):
        raise HarnessError(f"context identity must not sit under convention/: {ctx_id!r}")
    return hold_id, con_id, ctx_id


def deeper_convention_omit_identity(shallow_id: str) -> str:
    """``convention/<dir>/<leaf>`` that sorts after a one-segment convention identity.

    *shallow_id* is ``convention/`` plus one segment. The result is one
    directory under ``convention/`` and one leaf, so a default that fires
    only for a single segment does not cover it. Neither identity contains
    the other.
    """
    parts = shallow_id.split("/")
    if len(parts) != 2 or parts[0] != "convention" or not parts[1]:
        raise HarnessError(
            "shallow convention identity must be convention/ plus one "
            f"segment: {shallow_id!r}"
        )
    shallow_leaf = parts[1]
    dir_tok, leaf_tok = unique_compact("zdir", "zleaf")
    directory = f"z{dir_tok}"
    if "/" in directory or "/" in leaf_tok or not directory or not leaf_tok:
        raise HarnessError(
            "deeper convention segments must each be one path segment: "
            f"{directory!r} {leaf_tok!r}"
        )
    for segment in (directory, leaf_tok):
        if (
            shallow_leaf in segment
            or segment in shallow_leaf
            or segment in GOVERNANCE_TOKENS
        ):
            raise HarnessError(
                "deeper convention segment overlaps the shallow leaf or a "
                f"governance word: {shallow_leaf!r} vs {segment!r}"
            )
    deep_id = f"convention/{directory}/{leaf_tok}"
    deep_parts = deep_id.split("/")
    if deep_parts != ["convention", directory, leaf_tok]:
        raise HarnessError(
            "deeper convention identity is not convention/<dir>/<leaf>: "
            f"{deep_id!r}"
        )
    if shallow_id in deep_id or deep_id in shallow_id or not shallow_id < deep_id:
        raise HarnessError(
            "deeper convention identity must sort after the one-segment "
            f"identity and must not contain it: {shallow_id!r} vs {deep_id!r}"
        )
    return deep_id


def _build_prefix_sharing_convention_omit_identity(*others: str) -> str:
    """``convention<extra>/<leaf>``: the first segment only shares the prefix.

    The omit-default is the directory ``convention/``. The character
    immediately after those letters is not the slash that marks that
    directory, so this identity is not under it. The caller omits
    governance; the effective value is context.
    """
    extra = compact_token("al")
    leaf = compact_token("lf")
    if (
        not extra.isalnum()
        or not leaf.isalnum()
        or extra == leaf
        or extra in leaf
        or leaf in extra
        or "convention" in extra
        or "convention" in leaf
    ):
        raise HarnessError(
            "prefix-sharing convention segments must be distinct "
            f"alphanumeric tokens that do not repeat the directory name: "
            f"{extra!r} {leaf!r}"
        )
    first = f"convention{extra}"
    boundary = len("convention")
    if (
        not first.startswith("convention")
        or len(first) <= boundary
        or first[boundary] == "/"
        or "/" in first
        or first == "convention"
    ):
        raise HarnessError(
            "prefix-sharing first segment must begin with convention "
            f"without the directory slash: {first!r}"
        )
    ident = f"{first}/{leaf}"
    parts = ident.split("/")
    if parts != [first, leaf]:
        raise HarnessError(
            "prefix-sharing identity is not one directory and one leaf: "
            f"{ident!r}"
        )
    if ident.startswith("convention/") or not ident.startswith("convention"):
        raise HarnessError(
            "prefix-sharing identity must share the convention characters "
            f"and must not sit under convention/: {ident!r}"
        )
    for segment in parts:
        if segment.lower() in GOVERNANCE_TOKENS:
            raise HarnessError(
                "prefix-sharing segment is a governance word: "
                f"{segment!r} in {ident!r}"
            )
    seen = [ident]
    for other in others:
        if not other or not isinstance(other, str):
            raise HarnessError(
                "prefix-sharing overlap check needs a non-empty identity: "
                f"{other!r}"
            )
        if ident in other or other in ident:
            raise HarnessError(
                "prefix-sharing identity overlaps another planted identity: "
                f"{ident!r} vs {other!r}"
            )
        seen.append(other)
    if len(seen) != len(set(seen)):
        raise HarnessError(
            f"prefix-sharing identities are not unique: {seen!r}"
        )
    return ident


def prefix_sharing_convention_omit_identity(*others: str) -> str:
    """Omitted identity whose first segment shares the convention prefix only.

    Shape ``convention<extra>/<leaf>`` (the same boundary as
    ``conventional/<leaf>``). Not ``convention/<leaf>`` and not a
    code_ref. Retries when a generated token collides with *others*.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_prefix_sharing_convention_omit_identity(*others)
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        "could not build a prefix-sharing convention omit identity: "
        f"{last_error}"
    )


def prefix_sharing_human_omit_identity(
    hold_id: str,
    conv_id: str,
    deep_id: str,
    ctx_id: str,
) -> str:
    """Omitted identity for a human badge that is not under ``convention/``.

    The first segment only shares the ``convention`` characters (the same
    boundary as ``conventional/<leaf>``). The character after those letters
    is not the slash that marks the directory, so the omit-default is
    context, not constraint. Identity order places it after the nested
    ``convention/`` omit and after the declared context identity, so a
    path list that ties on governance puts this hit in the context group,
    after that earlier context hit. A badge that treats a leading
    ``convention`` string as the directory, without that slash, labels
    this hit constraint instead.
    """
    ident = prefix_sharing_convention_omit_identity(
        hold_id, conv_id, deep_id, ctx_id
    )
    if not (hold_id < ctx_id < conv_id < deep_id < ident):
        raise HarnessError(
            "prefix-sharing human omit must sort after the nested "
            "convention directory and after the declared context identity, "
            "so its context badge is not in the constraint group: "
            f"{hold_id!r} {ctx_id!r} {conv_id!r} {deep_id!r} {ident!r}"
        )
    return ident


def prefix_sharing_tool_omit_identity(nested_id: str, *others: str) -> str:
    """Omitted ``convention<extra>/<leaf>`` beside a nested convention identity.

    *nested_id* is ``convention/<dir>/<leaf>``. The result's first segment
    only shares the ``convention`` characters (the same boundary as
    ``conventional/<leaf>``), so the identity is not under that directory.
    It sorts after the nested identity. On the search tool the nested
    omission is constraint and this omission is context.
    """
    parts = nested_id.split("/")
    if len(parts) != 3 or parts[0] != "convention" or not all(parts):
        raise HarnessError(
            "tool prefix-sharing omit needs a convention/<dir>/<leaf> "
            f"sibling: {nested_id!r}"
        )
    ident = prefix_sharing_convention_omit_identity(nested_id, *others)
    if not nested_id < ident:
        raise HarnessError(
            "prefix-sharing tool omit must sort after the nested "
            f"convention identity: {nested_id!r} vs {ident!r}"
        )
    return ident


def inverted_nested_convention_identities() -> tuple[str, str, str, str]:
    """(hold, one-segment omit, deeper omit, other omit) not in identity sort.

    Ascending is hold, other, one-segment, deeper. Descending is the
    reverse. Required path rank is hold, then both omitted convention
    identities (constraint; one segment, then ``convention/<dir>/<leaf>``),
    then the other omit (context).
    """
    hold_id, con_id, ctx_id = inverted_convention_identities()
    deep_id = deeper_convention_omit_identity(con_id)
    required = (hold_id, con_id, deep_id, ctx_id)
    _order_disagrees_with_sort(required)
    if not (hold_id < ctx_id < con_id < deep_id):
        raise HarnessError(
            "nested convention identities did not land in the planned sort: "
            f"{hold_id!r} {ctx_id!r} {con_id!r} {deep_id!r}"
        )
    if ctx_id.startswith("convention/") or hold_id.startswith("convention/"):
        raise HarnessError(
            "only the omitted convention identities may sit under convention/: "
            f"hold={hold_id!r} context={ctx_id!r}"
        )
    _identities_do_not_overlap(required)
    return required


def inverted_tool_path_governance_identities() -> tuple[str, str, str]:
    """(hold slot, ``convention/<dir>/<leaf>``, identity outside that directory).

    Identity ascending is the hold slot, then the outside identity, then
    the nested convention identity. The required tool rank is hold, then
    the nested omission (constraint), then the outside omission (context).
    Treating both omissions as the same governance follows identity order
    and lists the outside identity before the nested one. The one-segment
    ``convention/<leaf>`` identity exists only to place the nested leaf
    and is not returned.
    """
    hold_id, shallow_id, outside_id = inverted_convention_identities()
    nested_id = deeper_convention_omit_identity(shallow_id)
    required = (hold_id, nested_id, outside_id)
    _order_disagrees_with_sort(required)
    if not (hold_id < outside_id < nested_id):
        raise HarnessError(
            "tool path identities did not land in the planned sort: "
            f"{hold_id!r} {outside_id!r} {nested_id!r}"
        )
    nested_parts = nested_id.split("/")
    if (
        nested_parts[0] != "convention"
        or len(nested_parts) != 3
        or any(not part for part in nested_parts)
    ):
        raise HarnessError(
            "nested omit is not convention/<dir>/<leaf>: "
            f"{nested_id!r}"
        )
    if outside_id.startswith("convention/") or hold_id.startswith("convention/"):
        raise HarnessError(
            "only the nested omit may sit under convention/: "
            f"hold={hold_id!r} outside={outside_id!r}"
        )
    if shallow_id in required or nested_id.startswith(shallow_id + "/"):
        raise HarnessError(
            "one-segment convention identity leaked into the tool triple "
            f"or is a directory prefix of the nested leaf: {shallow_id!r}"
        )
    if (hold_id, outside_id, nested_id) == required:
        raise HarnessError(
            "both-omission identity order matches the required tool rank"
        )
    _identities_do_not_overlap(required)
    return required


def numbered_identities(n: int, suffix: str) -> list[str]:
    """n lexicographically ordered identities that do not contain *suffix* twice."""
    if n < 1:
        raise HarnessError("numbered_identities requires n >= 1")
    width = max(3, len(str(n - 1)))
    identities = [f"n{i:0{width}d}{suffix}" for i in range(n)]
    if identities != sorted(identities):
        raise HarnessError(f"numbered identities are not sorted: {identities!r}")
    return identities


def abs_workspace_path(ws: Workspace, rel: str | Path) -> str:
    """Absolute path string under the workspace (file need not exist)."""
    return str((ws.path / rel).resolve())


@dataclass(frozen=True)
class FilesystemAbsoluteRelativeProbe:
    """Two generated relative code_refs, neither the public absolute sample.

    ``relative_ref`` and ``other_ref`` are plain relative paths. Neither
    begins with ``./`` or ``/``, neither is ``SAMPLE_FILE``, and
    neither is a suffix or a directory prefix of the other.
    """

    relative_ref: str
    other_ref: str


def _plain_relative_code_ref(ref: str) -> None:
    """Raise when *ref* is not a multi-segment relative path without globs."""
    if not ref or ref.startswith(("./", "/", ".")) or "\\" in ref or "*" in ref:
        raise HarnessError(f"relative ref is not a plain relative path: {ref!r}")
    parts = ref.split("/")
    if len(parts) < 2 or any(part in ("", ".", "..") for part in parts):
        raise HarnessError(f"relative ref is not a multi-segment relative path: {ref!r}")


def _refs_do_not_cover_each_other(left: str, right: str) -> None:
    """Neither ref is the other, a suffix of the other, or a directory prefix."""
    if left == right or left in right or right in left:
        raise HarnessError(f"relative refs overlap: {left!r} vs {right!r}")
    if left.endswith("/" + right) or right.endswith("/" + left):
        raise HarnessError(f"relative refs are suffixes of each other: {left!r} vs {right!r}")
    if left.startswith(right + "/") or right.startswith(left + "/"):
        raise HarnessError(
            f"relative refs are directory prefixes of each other: {left!r} vs {right!r}"
        )


def _build_filesystem_absolute_relative_probe() -> FilesystemAbsoluteRelativeProbe:
    directory, leaf, ext, other_dir, other_leaf, other_ext = unique_compact(
        "adr", "alf", "aex", "odr", "olf", "oex"
    )
    relative_ref = f"{directory}/{leaf}.{ext}"
    other_ref = f"{other_dir}/{other_leaf}.{other_ext}"
    for ref in (relative_ref, other_ref):
        _plain_relative_code_ref(ref)
        if (
            ref == _PUBLIC_ABSOLUTE_RELATIVE_REF
            or ref.endswith("/" + _PUBLIC_ABSOLUTE_RELATIVE_REF)
            or _PUBLIC_ABSOLUTE_RELATIVE_REF.endswith("/" + ref)
            or SAMPLE_PREFIX_DIR in ref
        ):
            raise HarnessError(
                f"generated relative ref collided with the public absolute "
                f"sample: {ref!r}"
            )
    _refs_do_not_cover_each_other(relative_ref, other_ref)
    return FilesystemAbsoluteRelativeProbe(
        relative_ref=relative_ref,
        other_ref=other_ref,
    )


def generated_filesystem_absolute_relative_probe() -> FilesystemAbsoluteRelativeProbe:
    """Two generated relative code_refs for a longer filesystem-absolute search.

    Neither ref is the fixed probe ``SAMPLE_FILE``. Fixture generation that
    cannot satisfy that raises; it does not return the fixed probe.
    """
    last_error: HarnessError | None = None
    for _ in range(8):
        try:
            return _build_filesystem_absolute_relative_probe()
        except HarnessError as exc:
            last_error = exc
    raise HarnessError(
        f"could not build a filesystem-absolute relative probe: {last_error}"
    )


def longer_filesystem_absolute_caller(
    ws: Workspace,
    relative_ref: str,
    *,
    absent_refs: Sequence[str] = (),
) -> str:
    """Workspace directory plus *relative_ref*, as one filesystem-absolute path.

    The prefix is a real absolute directory, longer than ``/``. Stripping
    one leading slash does not yield *relative_ref*. *absent_refs* are not
    suffixes of the caller path, and none of the ref segments appear in
    the prefix. The fixed probe ``SAMPLE_FILE`` is not a suffix.
    """
    text = str(relative_ref).replace("\\", "/")
    _plain_relative_code_ref(text)
    if text == _PUBLIC_ABSOLUTE_RELATIVE_REF:
        raise HarnessError(
            "filesystem-absolute caller reused the fixed relative probe"
        )
    prefix = str(ws.path.resolve()).replace("\\", "/")
    if not prefix.startswith("/") or prefix in ("", "/"):
        raise HarnessError(
            f"workspace prefix is not a longer absolute directory: {prefix!r}"
        )
    absolute = abs_workspace_path(ws, text).replace("\\", "/")
    expected = prefix.rstrip("/") + "/" + text
    if absolute != expected:
        raise HarnessError(
            f"absolute caller {absolute!r} is not the workspace prefix plus "
            f"the relative ref {expected!r}"
        )
    stripped = absolute[1:]
    if stripped == text or not stripped.endswith("/" + text):
        raise HarnessError(
            "stripping one leading slash collapsed the absolute caller onto "
            f"the relative ref: {absolute!r}"
        )
    prefix_parts = {part for part in prefix.split("/") if part}
    for other in (_PUBLIC_ABSOLUTE_RELATIVE_REF, *absent_refs):
        other_text = str(other).replace("\\", "/")
        if not other_text or other_text == text:
            continue
        if (
            absolute.endswith("/" + other_text)
            or ("/" + other_text + "/") in ("/" + stripped + "/")
        ):
            raise HarnessError(
                f"absolute caller {absolute!r} also covers {other_text!r}"
            )
    for ref in (text, *absent_refs):
        for part in str(ref).replace("\\", "/").split("/"):
            if part and part in prefix_parts:
                raise HarnessError(
                    f"absolute prefix {prefix!r} already contains ref segment {part!r}"
                )
    return absolute


def path_tokens_for_search(*paths: str | Path) -> list[str]:
    """Path spellings to strip from reports, including cwd and basenames."""
    tokens: list[str] = []
    for raw in paths:
        if raw is None:
            continue
        text = str(raw)
        if not text:
            continue
        tokens.append(text)
        tokens.append(text.replace("\\", "/"))
        tokens.append(os.path.abspath(text) if os.path.isabs(text) else text)
        base = os.path.basename(text.rstrip("/"))
        if base:
            tokens.append(base)
    return tokens
