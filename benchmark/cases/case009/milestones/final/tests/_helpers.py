"""Pipeline-owned sealed test helpers.

This file is the complete module. Import what you need (`from _helpers import ...`). Add a new helper here, with the imports and constants it closes over. Do not paste a sealed body into a feature file. Do not change a sealed name unless you own it and that feature's PRD was amended.
"""

from __future__ import annotations

import atexit
import base64
import ctypes
import errno
import fcntl
import hashlib
import json
import lzma
import os
import pty
import re
import select
import shutil
import stat
import struct
import subprocess
import sys
import threading
import time
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Iterator, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _harness import (  # noqa: E402
    RunResult,
    Workspace,
    loopback_http,
    product_bin_dir,
    reserve_loopback_port,
    token,
)

# Generic http(s) extractor. Does not pin product labels such as Endpoint=.
_HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class TwoRemoteLayout:
    """A pair of Git remotes with distinct runtime-generated HTTP URLs."""

    origin_url: str
    sibling_name: str
    sibling_url: str


# Dotted version token. Does not pin this checkout's version-number string.
_DOTTED_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)*")

# Version identity adjacent to a Git-Orbulk product name. Does not take a
# dotted token from Git's own version line or a Go runtime version that
# merely shares the same banner. Adjacency never crosses a line break: a
# product-name mention at the end of one line is not adjacent to a dotted
# token on the next line (such as Git's own version line in ``env``).
_IDENTITY_NEAR_PRODUCT_RE = re.compile(
    r"git[ \t\-]*orbulk[^\d\r\n]{0,32}(" + _DOTTED_VERSION_RE.pattern + r")",
    re.IGNORECASE,
)

# Product-name span. Hyphen, space, and case are not pinned.
_PRODUCT_NAME_RE = re.compile(r"git[\s\-]*orbulk", re.IGNORECASE)

# Remaining alphanumeric words after identity/product spans are stripped.
# A two-word slogan is not invocation guidance or a configuration report.
_MIN_SUBSTANCE_WORDS = 4


def _names_git_orbulk_product(text: str) -> bool:
    """True when *text* names the Git Orbulk product, ignoring hyphen/space/case."""
    collapsed = re.sub(r"[^a-z0-9]+", "", text.casefold())
    return "orbulk" in collapsed


def build_identity_token(text: str) -> str:
    """Return the version-identity token from Git-Orbulk-named presentations.

    Reads only *text*. A dotted token that is not next to a Git Orbulk product
    name is ignored (Git's own version, a Go runtime version). Multiple
    Git-Orbulk-named presentations that disagree are a hard failure, never a
    silent pick.
    """
    assert text.strip(), "no text from which to read version identity"
    assert _names_git_orbulk_product(text), "text does not name Git Orbulk"
    matches = list(_IDENTITY_NEAR_PRODUCT_RE.finditer(text))
    assert matches, (
        "no version identity token in a Git-Orbulk-named presentation"
    )
    tokens = [match.group(1) for match in matches]
    unique = list(dict.fromkeys(tokens))
    assert len(unique) == 1, (
        "Git-Orbulk-named presentations disagree on identity token: "
        f"{unique!r}"
    )
    return unique[0]


def require_success(result: RunResult) -> RunResult:
    """Fail if *result* is not a successful process exit.

    A non-zero status is never mapped to empty output. The stderr of the
    failed run is included in the assertion message.
    """
    assert result.returncode == 0, (
        f"expected success, got exit {result.returncode} "
        f"argv={list(result.argv)!r}: {result.stderr_text}"
    )
    return result


def assert_success(result: RunResult) -> RunResult:
    """Require a successful process exit.

    Same contract as ``require_success``. The name is the verdict the
    suite-bailout audit can see: a non-zero listing is not a named path.
    """
    return require_success(result)


def require_version_identity_of_this_build(result: RunResult) -> str:
    """Require the version path to report this build is Git Orbulk plus identity.

    Observed on the version path itself (FP-01). Does not consult the
    environment report. Does not pin banner wording, GOOS, or a specific
    version-number string. Returns the identity token from Git-Orbulk-named
    presentations, not a raw stdout line.
    """
    require_success(result)
    text = result.stdout_text
    assert text.strip(), "version path reported no identity on stdout"
    return build_identity_token(text)


# Feature tests call this name so the invocation itself is a check.
check_version_identity_of_this_build = require_version_identity_of_this_build


def require_version_path_identity_token(result: RunResult) -> str:
    """Require version-path identity of this build (FP-01).

    Success, names Git Orbulk, and returns the identity token from Git-Orbulk-
    named presentations. Does not read the environment report, does not
    require a first-line substring, and does not pin banner wording.
    """
    require_success(result)
    text = result.stdout_text
    assert text.strip(), "version path reported no identity on stdout"
    return build_identity_token(text)


check_version_path_identity_token = require_version_path_identity_token


def _strip_unrelated_tokens(text: str, tokens: Sequence[str]) -> str:
    """Remove *tokens* from *text*, longest first so prefixes do not nibble."""
    ordered = sorted((t for t in tokens if t), key=len, reverse=True)
    result = text
    for item in ordered:
        result = result.replace(item, "")
        stripped = item.rstrip("/")
        if stripped and stripped != item:
            result = result.replace(stripped, "")
    return result


def related_facts_without_dedicated(
    report: str,
    *,
    dedicated_urls: Sequence[str],
    git_remote_urls: Sequence[str],
    extra_unrelated: Sequence[str] = (),
) -> str:
    """Return env-report text after removing dedicated indications and extras.

    Strips dedicated would-use-server URLs, Git remote URLs, and caller-
    injected unrelated tokens (override URLs, filter command strings).
    Remaining text is the related-facts carrier for build identity. An
    empty remainder is a hard failure: that is not "no identity".
    """
    assert report.strip(), (
        "environment report is empty; no related facts remain after "
        "stripping dedicated indications"
    )
    remainder = _strip_unrelated_tokens(
        report,
        [*dedicated_urls, *git_remote_urls, *extra_unrelated],
    )
    assert remainder.strip(), (
        "stripping dedicated indications and unrelated tokens left no "
        "related environment facts"
    )
    return remainder


def require_identity_agrees_with_env_related_facts(
    version_result: RunResult,
    report: str,
    *,
    dedicated_urls: Sequence[str],
    git_remote_urls: Sequence[str],
    extra_unrelated: Sequence[str] = (),
) -> str:
    """Require version-path and env related-fact identity tokens to agree.

    Agreement is of the Git-Orbulk identity token, not of a dedicated
    indication URL, a Git remote URL, or an injected unrelated token.
    Does not require the version banner's wording or first line to appear
    in the environment report.
    """
    version_token = require_version_identity_of_this_build(version_result)
    related = related_facts_without_dedicated(
        report,
        dedicated_urls=dedicated_urls,
        git_remote_urls=git_remote_urls,
        extra_unrelated=extra_unrelated,
    )
    related_token = build_identity_token(related)
    unrelated = [
        item
        for item in (*dedicated_urls, *git_remote_urls, *extra_unrelated)
        if item
    ]
    for item in unrelated:
        assert version_token != item and related_token != item, (
            "identity agreement was an unrelated related-fact token "
            f"{item!r}, not this build's Git Orbulk identity"
        )
    assert version_token == related_token, (
        "version path identity disagrees with the environment report's "
        f"related-fact identity: version={version_token!r} "
        f"related={related_token!r}"
    )
    return version_token


def require_usage_information(
    result: RunResult, topic: str | None = None
) -> RunResult:
    """Require user-facing usage information, not a success banner.

    Names the Git Orbulk entry and emits more than one line of invocation
    guidance. Does not pin a Usage: heading, synopsis literal, or layout.
    When *topic* is set, per-command help must cover that subcommand.
    """
    require_success(result)
    text = result.stdout_text
    assert text.strip(), (
        "invocation produced no user-facing usage information"
    )
    assert _names_git_orbulk_product(text), (
        "usage information did not name the Git Orbulk entry"
    )
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 2, (
        "usage information was a single-line banner, not user-facing usage"
    )
    if topic:
        assert topic.casefold() in text.casefold(), (
            f"per-command help did not present usage for {topic!r}"
        )
    return result


check_usage_information = require_usage_information


def _substance_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _strip_git_orbulk_identity_spans(text: str) -> str:
    """Remove Git-Orbulk product-name spans and dotted identity tokens.

    Does not pin banner wording. Remaining text is the carrier that
    distinguishes usage or configuration from an identity dump.
    """
    stripped = _IDENTITY_NEAR_PRODUCT_RE.sub(" ", text)
    stripped = _PRODUCT_NAME_RE.sub(" ", stripped)
    stripped = _DOTTED_VERSION_RE.sub(" ", stripped)
    return stripped


def _strip_whole_word(text: str, word: str) -> str:
    """Remove whole-word *word* only. Prefixes such as environment stay."""
    if not word:
        return text
    return re.sub(
        r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])",
        " ",
        text,
        flags=re.IGNORECASE,
    )


def require_invocation_guidance_usage(
    result: RunResult, topic: str | None = None
) -> RunResult:
    """Require invocation-guidance usage, not a product or identity dump.

    FP-01: a no-subcommand invocation and help yield user-facing usage
    information, distinct from a Git Orbulk identity presentation. Does not
    pin a Usage: heading, synopsis literal, or layout.

    When *topic* is set, per-command help must still contain guidance
    after the topic name and product identity are stripped — naming the
    topic, or the product, is not coverage.
    """
    require_usage_information(result, topic=topic)
    remainder = _strip_git_orbulk_identity_spans(result.stdout_text)
    if topic:
        remainder = _strip_whole_word(remainder, topic)
    leftover_lines = [ln for ln in remainder.splitlines() if ln.strip()]
    words = _substance_words(remainder)
    assert leftover_lines, (
        "stdout was a Git Orbulk identity or product dump, not user-facing "
        "usage information"
    )
    if topic is None:
        # Suite / no-subcommand usage must still be guidance after the
        # identity presentation is removed. Per-command help may be a
        # short description once the topic name and product identity
        # are stripped; requiring two leftover lines would fail a
        # synopsis-plus-one-line description.
        assert len(leftover_lines) >= 2, (
            "usage information collapsed to a product banner once identity "
            "was removed; invocation guidance must remain"
        )
        assert len(words) >= _MIN_SUBSTANCE_WORDS, (
            "usage information was a short product slogan, not invocation "
            f"guidance (substance={words!r})"
        )
    return result


check_invocation_guidance_usage = require_invocation_guidance_usage


def require_env_configuration_report(result: RunResult) -> str:
    """Require ``env`` to print a configuration report, not a bare success.

    Filter summary and related facts still apply with no remotes. Does not
    demand a dedicated would-use-server indication when there are no remotes.
    """
    require_success(result)
    text = result.stdout_text
    assert text.strip(), (
        "environment-report subcommand printed no effective Git Orbulk-related "
        "configuration"
    )
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 2, (
        "environment report was not a configuration report"
    )
    return text


check_env_configuration_report = require_env_configuration_report


def require_env_effective_configuration(result: RunResult) -> str:
    """Require effective Git Orbulk-related configuration, not an identity dump.

    Filter summary and related facts still apply with no remotes (FP-01).
    Related facts must present this build's Git Orbulk identity. Does not
    demand a dedicated would-use-server indication. Does not pin
    related-fact labels or layout.
    """
    text = require_env_configuration_report(result)
    build_identity_token(text)
    remainder = _strip_git_orbulk_identity_spans(text)
    leftover_lines = [ln for ln in remainder.splitlines() if ln.strip()]
    words = _substance_words(remainder)
    assert leftover_lines and len(leftover_lines) >= 2, (
        "environment report was a Git Orbulk identity dump, not effective "
        "Git Orbulk-related configuration"
    )
    assert len(words) >= _MIN_SUBSTANCE_WORDS, (
        "environment report had no configuration substance beyond a "
        f"product slogan (substance={words!r})"
    )
    return text


check_env_effective_configuration = require_env_effective_configuration


def require_git_config_set(
    ws: Workspace,
    key: str,
    value: str,
    *,
    local: bool = False,
    global_: bool = False,
) -> RunResult:
    """Write a Git config value and fail if Git itself rejected the write."""
    result = ws.git_config_set(key, value, local=local, global_=global_)
    assert result.returncode == 0, (
        f"git config {key!r} failed (exit {result.returncode}): "
        f"{result.stderr_text}"
    )
    return result


def require_rejected_unlike_clean(clean: RunResult, dirty: RunResult) -> RunResult:
    """Require that *dirty* is a refused invocation relative to *clean*.

    The live baseline (*clean*) must succeed. The dirty run must exit
    non-zero, write a non-empty error on stderr, and be distinguishable
    from the clean run. Does not pin an exit code or message text.
    """
    assert clean.returncode == 0, (
        "live baseline must succeed before a refusal can be measured, "
        f"got exit {clean.returncode}: {clean.stderr_text}"
    )
    assert dirty.returncode != 0, (
        "expected a non-zero exit after an undefined token, "
        f"got {dirty.returncode}; stdout={dirty.stdout_text!r} "
        f"stderr={dirty.stderr_text!r}"
    )
    assert dirty.stderr_text.strip(), (
        "expected a clear error on standard error; "
        f"stdout={dirty.stdout_text!r} stderr={dirty.stderr_text!r}"
    )
    assert (dirty.returncode, dirty.stdout, dirty.stderr) != (
        clean.returncode,
        clean.stdout,
        clean.stderr,
    ), "dirty invocation was not distinguishable from the same entry without the token"
    return dirty


def runtime_http_url(label: str, path: str | None = None) -> str:
    """Return a runtime-unique ``https://`` URL on the ``.example.test`` TLD.

    *label* is a hostname segment (not a product symbol). Host and path each
    include a fresh token so public samples cannot enumerate the URL.
    """
    if not label:
        raise ValueError("label must be non-empty")
    if path is None:
        path = f"{token()}/repo.git"
    path = str(path).lstrip("/")
    return f"https://{token()}.{label}.example.test/{path}"


def add_git_remote(ws: Workspace, name: str, url: str) -> None:
    """Add a Git remote. A failed ``git remote add`` is not treated as absence."""
    result = ws.git(["remote", "add", name, url])
    assert result.returncode == 0, (
        f"git remote add {name!r} {url!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )


def make_two_remote_layout() -> TwoRemoteLayout:
    """Build origin + named-sibling URLs without writing them to a repository."""
    return TwoRemoteLayout(
        origin_url=runtime_http_url("alpha"),
        sibling_name=f"sib_{token()}",
        sibling_url=runtime_http_url("beta"),
    )


def install_two_remote_layout(
    ws: Workspace, layout: TwoRemoteLayout
) -> TwoRemoteLayout:
    """Init a repository and add the two remotes from *layout*."""
    ws.init_repo()
    add_git_remote(ws, "origin", layout.origin_url)
    add_git_remote(ws, layout.sibling_name, layout.sibling_url)
    return layout


def env_report(ws: Workspace) -> str:
    """Run ``git orbulk env`` and return stdout. Only a zero exit is a report."""
    result = ws.invoke_via_git(["env"])
    require_success(result)
    return result.stdout_text


def _strip_url_trailer(raw: str) -> str:
    return raw.rstrip(".,;:)")


def _extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in _HTTP_URL_RE.finditer(text):
        url = _strip_url_trailer(match.group(0))
        if url:
            found.append(url)
    return found


def _unique_urls(urls: Sequence[str]) -> list[str]:
    seen: list[str] = []
    seen_keys: set[str] = set()
    for url in urls:
        key = url.rstrip("/")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        seen.append(url)
    return seen


_PUSHURL_ECHO = re.compile(
    r"(?:^|\s)(?:git\s+config\s+)?\S*pushurl\s*=",
    re.IGNORECASE,
)


# Upload-side marker word on a report line, outside any URL text. The
# Contract lets ``env`` also present an upload endpoint on a line that
# carries the word ``push`` or ``upload``; the endpoint line never does.
# Case is free; the word may also lead a camel-case or key spelling
# (``PushEndpoint``, ``lfs.pushurl``, ``remote.<r>.lfspushurl``).
_UPLOAD_SIDE_WORD = re.compile(
    r"(?<![A-Za-z0-9])(?i:lfs)?(?i:push(?:url)?|upload)(?![a-z0-9])"
)


def _is_upload_side_line(line: str) -> bool:
    """True when *line* (URLs removed) names the push/upload side."""
    outside_urls = _HTTP_URL_RE.sub(" ", line)
    return bool(_UPLOAD_SIDE_WORD.search(outside_urls))


def _drop_pushurl_echo_lines(report: str) -> str:
    """Drop push-URL echoes and upload-endpoint lines from the report.

    A configuration echo that only restates a *pushurl= value, and a line
    that presents the upload endpoint, are not the endpoint line. Do not
    drop ordinary ``*.url=`` lines: those may be the real endpoint.
    """
    kept: list[str] = []
    for line in report.splitlines():
        if _PUSHURL_ECHO.search(line.strip()):
            continue
        if _is_upload_side_line(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _urls_on_lines_containing(report: str, needle: str) -> list[str]:
    found: list[str] = []
    for line in report.splitlines():
        if needle in line:
            found.extend(_extract_urls(line))
    return found


def _url_equals(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _pick_dedicated(urls: Sequence[str], git_remote_url: str) -> str:
    """Choose the dedicated server URL from observations on one remote.

    If both the Git remote URL and another URL are present, the Git remote
    URL is a related fact (remote listing) and the remaining URL is the
    dedicated indication. A sole URL that equals the Git remote listing is
    not a dedicated would-use-server indication. Multiple distinct remaining
    URLs cannot be classified and are a hard failure, never a silent pick.
    """
    unique = _unique_urls(urls)
    assert unique, "no HTTP(S) URL observation for this remote"
    remaining = [u for u in unique if not _url_equals(u, git_remote_url)]
    remaining = _unique_urls(remaining)
    assert remaining, (
        "no dedicated would-use-server URL distinct from the Git remote "
        f"listing (git remote {git_remote_url!r}; observations {unique!r})"
    )
    assert len(remaining) == 1, (
        "cannot classify a dedicated server indication: multiple distinct "
        f"non-git-remote URLs {remaining!r} (git remote {git_remote_url!r})"
    )
    return remaining[0]


def dedicated_server_url(
    report: str,
    *,
    remote_name: str,
    git_remote_url: str,
    other_remote_name: str | None = None,
) -> str:
    """Return the Git Orbulk server URL dedicated to *remote_name* in *report*.

    Association rules (form-open; does not match a product label):

    * Named remotes other than ``origin``: observations are lines that
      carry both the remote name and an HTTP(S) URL. The Git remote URL on
      those lines is a related fact when another URL is also present.
      A named remote that only lists its Git remote URL has no dedicated
      indication.
    * Default remote ``origin``: the report is not required to contain the
      word ``origin``. The dedicated indication is the would-use-server
      URL that is not on the sibling remote's named observations, and is
      not merely the origin Git remote listing.
    """
    report = _drop_pushurl_echo_lines(report)
    if not report.strip():
        raise AssertionError(
            f"environment report is empty; no dedicated indication for "
            f"remote {remote_name!r}"
        )
    if remote_name != "origin":
        named = _urls_on_lines_containing(report, remote_name)
        assert named, (
            f"no URL observation naming remote {remote_name!r} in report"
        )
        return _pick_dedicated(named, git_remote_url)

    unlabeled: list[str] = []
    for line in report.splitlines():
        if other_remote_name and other_remote_name in line:
            continue
        unlabeled.extend(_extract_urls(line))
    assert unlabeled, (
        "no would-use-server URL observation for the default remote "
        f"(git remote {git_remote_url!r})"
    )
    return _pick_dedicated(unlabeled, git_remote_url)


def indication_names(observed: str, url: str) -> bool:
    """True when *observed* names *url* as the server that would be used."""
    if not observed or not url:
        return False
    return url.rstrip("/") in observed.rstrip("/")


def path_without_product_bin(
    env: Mapping[str, str],
    *,
    root: Path | None = None,
) -> str:
    """Return PATH with the recipe product ``bin/`` directory removed."""
    bin_dir = str(product_bin_dir(root=root).resolve())
    parts: list[str] = []
    for part in env.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        try:
            resolved = str(Path(part).resolve())
        except OSError:
            resolved = part
        if resolved == bin_dir or part == bin_dir:
            continue
        parts.append(part)
    return os.pathsep.join(parts)


# ---------------------------------------------------------------------------
# F02: install / uninstall / update
# ---------------------------------------------------------------------------

HOOK_TYPES = ("pre-push", "post-checkout", "post-commit", "post-merge")
FILTER_KEYS = (
    "filter.lfs.clean",
    "filter.lfs.smudge",
    "filter.lfs.process",
)

_GIT_VERSION_RE = re.compile(
    r"git version (\d+)\.(\d+)(?:\.(\d+))?",
    re.IGNORECASE,
)


def require_points_at_git_orbulk(text: str) -> str:
    """Require a non-empty Git config/hook value that names Git Orbulk."""
    assert text, "expected a non-empty value pointing at Git Orbulk"
    assert _names_git_orbulk_product(text), (
        "value does not name Git Orbulk as the filter/hook target: "
        f"{text!r}"
    )
    return text


def git_version_tuple(ws: Workspace) -> tuple[int, int, int]:
    """Return this Git's (major, minor, patch). Probe failure is not absence."""
    result = ws.git(["version"])
    assert result.returncode == 0, (
        f"git version failed (exit {result.returncode}): {result.stderr_text}"
    )
    match = _GIT_VERSION_RE.search(result.stdout_text)
    assert match, (
        "cannot parse Git version from "
        f"{result.stdout_text!r} {result.stderr_text!r}"
    )
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or "0")
    return (major, minor, patch)


def git_version_at_least(
    ws: Workspace, major: int, minor: int, patch: int = 0
) -> bool:
    """True when this Git is at least *major*.*minor*.*patch*."""
    return git_version_tuple(ws) >= (major, minor, patch)


def lookup_git_config(
    ws: Workspace,
    key: str,
    *,
    local: bool = False,
    global_: bool = False,
    file: str | Path | None = None,
    worktree: bool = False,
    system: bool = False,
    env_updates: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> str | None:
    """Read one Git config key with Rule-1 classified absence.

    ``git config --get``: exit 0 is a found value (empty string is empty,
    not missing); exit 1 is unset (``None``); any other status hard-fails
    with Git's stderr. Exactly one scope must be selected.
    """
    scopes = sum(
        [
            bool(local),
            bool(global_),
            file is not None,
            bool(worktree),
            bool(system),
        ]
    )
    assert scopes == 1, (
        "lookup_git_config requires exactly one of local, global_, file, "
        f"worktree, system (got {scopes})"
    )
    argv: list[str] = ["config"]
    if file is not None:
        argv.extend(["--file", str(file)])
    elif local:
        argv.append("--local")
    elif global_:
        argv.append("--global")
    elif worktree:
        argv.append("--worktree")
    elif system:
        argv.append("--system")
    argv.extend(["--get", key])
    result = ws.git(argv, env_updates=env_updates, cwd=cwd)
    if result.returncode == 0:
        text = result.stdout_text
        if text.endswith("\n"):
            text = text[:-1]
        return text
    if result.returncode == 1:
        return None
    raise AssertionError(
        f"git config --get {key!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )


def require_filters_point_at_git_orbulk(
    ws: Workspace, **scope
) -> dict[str, str]:
    """Require clean/smudge/process in *scope* each name Git Orbulk."""
    found: dict[str, str] = {}
    for key in FILTER_KEYS:
        value = lookup_git_config(ws, key, **scope)
        assert value is not None, (
            f"{key} is unset in the requested Git config scope"
        )
        found[key] = require_points_at_git_orbulk(value)
    return found


def require_filters_unset(ws: Workspace, **scope) -> None:
    """Require clean/smudge/process are unset (Git --get exit 1) in *scope*."""
    for key in FILTER_KEYS:
        value = lookup_git_config(ws, key, **scope)
        assert value is None, (
            f"{key} still set in the requested scope: {value!r}"
        )


def foreign_filter_command() -> str:
    """Runtime-unique filter command that does not name Git Orbulk."""
    return f"cmd_{token()}"


def foreign_hook_body() -> str:
    """Runtime-unique non-empty hook body that is not a Git Orbulk script."""
    return f"custom-hook-{token()}\n"


def isolated_system_scope(
    ws: Workspace,
) -> tuple[dict[str, str | None], Path]:
    """Return env updates plus a HOME-local file for ``GIT_CONFIG_SYSTEM``."""
    path = ws.home / f"syscfg_{token()}"
    path.write_text("", encoding="utf-8")
    return (
        {
            "GIT_CONFIG_NOSYSTEM": None,
            "GIT_CONFIG_SYSTEM": str(path),
        },
        path,
    )


def hooks_dir(ws: Workspace, relpath: str | None = None) -> Path:
    """Resolve the default ``.git/hooks`` directory or a relative hooks-path."""
    if relpath is None:
        return ws.resolve(".git/hooks")
    return ws.resolve(relpath)


def _hook_relpath(hook_type: str, hooks_relpath: str | None = None) -> str:
    base = ".git/hooks" if hooks_relpath is None else hooks_relpath.rstrip("/")
    return f"{base}/{hook_type}"


def read_hook(
    ws: Workspace, hook_type: str, *, hooks_relpath: str | None = None
) -> str:
    """Read a hook file. Missing is ``FileNotFoundError``, never empty-as-absent."""
    return ws.read(_hook_relpath(hook_type, hooks_relpath))


def write_hook(
    ws: Workspace,
    hook_type: str,
    body: str,
    *,
    hooks_relpath: str | None = None,
) -> Path:
    """Write a hook file (empty *body* is an empty existing file)."""
    return ws.write(_hook_relpath(hook_type, hooks_relpath), body)


def require_hook_absent(
    ws: Workspace, hook_type: str, *, hooks_relpath: str | None = None
) -> None:
    """Require that *hook_type* is not present as a regular file."""
    try:
        body = read_hook(ws, hook_type, hooks_relpath=hooks_relpath)
    except FileNotFoundError:
        return
    raise AssertionError(
        f"expected {hook_type} hook to be absent, found {body!r}"
    )


def require_hooks_absent(
    ws: Workspace, *, hooks_relpath: str | None = None
) -> None:
    """Require that none of the four Git Orbulk hook types exist."""
    for hook_type in HOOK_TYPES:
        require_hook_absent(ws, hook_type, hooks_relpath=hooks_relpath)


def require_hook_invokes_git_orbulk(body: str) -> str:
    """Require a non-empty hook body that names Git Orbulk."""
    assert body, "hook body is empty; it does not invoke Git Orbulk"
    assert _names_git_orbulk_product(body), (
        "hook body does not name Git Orbulk: "
        f"{body!r}"
    )
    return body


def read_git_orbulk_hook_bodies(
    ws: Workspace, *, hooks_relpath: str | None = None
) -> dict[str, str]:
    """Read the four hook files after a successful install/update.

    Each body must invoke Git Orbulk. Does not require the four bodies to
    stay pairwise distinct after product-name or identity spans are
    removed: a shared body that still invokes Git Orbulk for whichever
    hook Git ran satisfies the written contract.
    """
    bodies: dict[str, str] = {}
    for hook_type in HOOK_TYPES:
        body = read_hook(ws, hook_type, hooks_relpath=hooks_relpath)
        bodies[hook_type] = require_hook_invokes_git_orbulk(body)
    return bodies


def capture_standard_hook_bodies(
    ws: Workspace, *, hooks_relpath: str | None = None
) -> dict[str, str]:
    """Read the four hook files after a successful install/update.

    Each body must invoke Git Orbulk. After product-name and identity spans
    are removed, the four bodies must still be pairwise distinct.
    """
    bodies: dict[str, str] = {}
    stripped: dict[str, str] = {}
    for hook_type in HOOK_TYPES:
        body = read_hook(ws, hook_type, hooks_relpath=hooks_relpath)
        bodies[hook_type] = require_hook_invokes_git_orbulk(body)
        stripped[hook_type] = _strip_git_orbulk_identity_spans(body)
    unique = set(stripped.values())
    assert len(unique) == len(HOOK_TYPES), (
        "standard hook bodies were not pairwise distinct after removing "
        f"product-name and identity spans: {stripped!r}"
    )
    return bodies


def require_hook_equals_standard(
    ws: Workspace,
    hook_type: str,
    standard: Mapping[str, str],
    *,
    hooks_relpath: str | None = None,
) -> str:
    """Require *hook_type* equals the captured current-standard body."""
    assert hook_type in standard, (
        f"no captured standard body for {hook_type!r}"
    )
    body = read_hook(ws, hook_type, hooks_relpath=hooks_relpath)
    assert body == standard[hook_type], (
        f"{hook_type} hook is not the captured current standard body"
    )
    return body


def caller_visible(result: RunResult) -> str:
    """Stdout plus stderr text. Does not pin which channel carried guidance."""
    return result.stdout_text + result.stderr_text


def require_hook_integration_guidance(
    result: RunResult,
    *,
    unlike: Sequence[RunResult],
    strip_tokens: Sequence[str],
) -> str:
    """Require caller-visible hook-integration guidance on a conflict path.

    Visible output must be non-empty, differ from each *unlike* run, and
    remain non-empty after *strip_tokens* (foreign bodies, absolute paths)
    are removed. Does not pin wording, channel, or a hook-script dump.
    """
    visible = caller_visible(result)
    assert visible.strip(), (
        "manual conflict path emitted no caller-visible hook-integration "
        "guidance"
    )
    for other in unlike:
        other_visible = caller_visible(other)
        assert visible != other_visible, (
            "hook-integration guidance was not distinguishable from a "
            "comparison run"
        )
    remainder = _strip_unrelated_tokens(visible, strip_tokens)
    assert remainder.strip(), (
        "hook-integration guidance vanished after stripping foreign bodies "
        "and paths; no stable carrier remained"
    )
    return remainder


def guidance_identifies_hook_contrast(
    result_a: RunResult,
    result_b: RunResult,
    *,
    strip_tokens: Sequence[str],
    hook_a: str,
    hook_b: str,
) -> tuple[str, str]:
    """Require remaining guidance to identify each blocked hook type.

    After *strip_tokens* are removed, each arm's remaining output must
    still name that arm's blocked hook type. A complete dump that names
    every hook type still names the blocked one. Does not require the two
    remainders to differ, and does not pin wording.
    """
    rem_a = _strip_unrelated_tokens(caller_visible(result_a), strip_tokens)
    rem_b = _strip_unrelated_tokens(caller_visible(result_b), strip_tokens)
    assert rem_a.strip(), (
        f"no remaining guidance identifying blocked hook {hook_a!r}"
    )
    assert rem_b.strip(), (
        f"no remaining guidance identifying blocked hook {hook_b!r}"
    )
    assert hook_a in rem_a, (
        "remaining guidance does not identify the blocked hook-integration "
        f"task {hook_a!r}"
    )
    assert hook_b in rem_b, (
        "remaining guidance does not identify the blocked hook-integration "
        f"task {hook_b!r}"
    )
    return rem_a, rem_b


def require_guidance_remainder_unlike_runs(
    result: RunResult,
    unlike: Sequence[RunResult],
    *,
    strip_tokens: Sequence[str],
) -> str:
    """Require remaining guidance differs from each *unlike* remainder.

    After *strip_tokens* (foreign bodies, absolute paths) are removed,
    *result*'s remainder must be non-empty and differ from each comparison
    run's remainder. Path covariates are not a sufficient unlike. Leftover
    whitespace from token excision is not a difference. Does not pin wording.
    """
    remainder = _strip_unrelated_tokens(caller_visible(result), strip_tokens)
    carrier = " ".join(remainder.split())
    assert carrier, (
        "hook-integration guidance vanished after stripping foreign bodies "
        "and paths; no stable carrier remained"
    )
    for other in unlike:
        other_remainder = _strip_unrelated_tokens(
            caller_visible(other), strip_tokens
        )
        other_carrier = " ".join(other_remainder.split())
        assert carrier != other_carrier, (
            "remaining hook-integration guidance was not distinguishable "
            "from a comparison run after stripping foreign bodies and paths"
        )
    return remainder


def _option_token_covariates(*results: RunResult) -> list[str]:
    """Argv option tokens that can echo into caller-visible output.

    Collects ``-``/``--`` flags from each compared run. Does not include
    ``-`` or ``--`` alone. Does not pin flag wording in the product output.
    """
    tokens: list[str] = []
    seen: set[str] = set()
    for result in results:
        for arg in result.argv:
            text = str(arg)
            if not text.startswith("-") or text in ("-", "--"):
                continue
            if text not in seen:
                seen.add(text)
                tokens.append(text)
    return tokens


def require_guidance_remainder_unlike_option_covariates(
    result: RunResult,
    unlike: Sequence[RunResult],
    *,
    strip_tokens: Sequence[str],
) -> str:
    """Require remaining guidance unlike each run after option-token strip.

    After foreign-body tokens, absolute-path tokens, and option-token
    covariates from *result* and each *unlike* run are removed, *result*'s
    remainder must be non-empty and differ from each comparison run's
    remainder. Echoing ``--manual`` versus ``--zxq-*``, or a workspace
    path, is not a sufficient unlike. Leftover whitespace from token
    excision is not a difference. Does not pin wording.
    """
    assert unlike, "need at least one unlike run"
    option_tokens = _option_token_covariates(result, *unlike)
    combined = [*strip_tokens, *option_tokens]
    remainder = _strip_unrelated_tokens(caller_visible(result), combined)
    carrier = " ".join(remainder.split())
    assert carrier, (
        "hook-integration guidance vanished after stripping foreign bodies, "
        "paths, and option-token covariates; no stable carrier remained"
    )
    for other in unlike:
        other_remainder = _strip_unrelated_tokens(
            caller_visible(other), combined
        )
        other_carrier = " ".join(other_remainder.split())
        assert carrier != other_carrier, (
            "remaining hook-integration guidance was not distinguishable "
            "from a comparison run after stripping foreign bodies, paths, "
            "and option-token covariates"
        )
    return remainder


# ---------------------------------------------------------------------------
# F03: pointer format and pointer plumbing
# ---------------------------------------------------------------------------

_POINTER_KEY_RE = re.compile(r"^[a-z0-9.-]+$")
_POINTER_KV_LINE_RE = re.compile(r"^[a-z0-9.-]+ .+$")
_GIT_BLOB_HEX_RE = re.compile(r"\b[0-9a-f]{40}(?:[0-9a-f]{24})?\b")


def sha256_hex(data: bytes) -> str:
    """Independent SHA-256 lowercase hex of *data*. Not a pointer encoder."""
    return hashlib.sha256(data).hexdigest()


def join_pointer_kv(pairs: Sequence[tuple[str, str]]) -> bytes:
    """Serialize key/value pairs as Unix-newline pointer lines."""
    return "".join(f"{key} {value}\n" for key, value in pairs).encode("utf-8")


def contract_still_readable_legacy_pre_release_version_identifier() -> str:
    """Interface Contract still-readable leftover pre-release version identifier.

    FP-03: newly written pointers use the current v1
    identifier, which is distinct from this leftover pre-release
    identifier. Substituting this Contract token into an otherwise
    generated pointer is ordinary-check success and strict-check
    valid-but-not-canonical. Not some other still-readable alias.
    Does not return the current v1 identifier.
    """
    return "https://cordage.example.com/spec/v1"


def parse_pointer_kv(document: bytes) -> list[tuple[str, str]]:
    """Parse a pointer document into ``(key, value)`` pairs.

    An empty document is the empty-pointer passthrough and yields ``[]``.
    A nonempty document that is not key/value lines is a hard failure.
    """
    if document == b"":
        return []
    try:
        text = document.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"pointer document is not UTF-8: {exc}") from exc
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    assert lines, (
        "nonempty pointer document had no key/value lines: "
        f"{document!r}"
    )
    pairs: list[tuple[str, str]] = []
    for line in lines:
        if line.endswith("\r"):
            line = line[:-1]
        parts = line.split(" ", 1)
        assert len(parts) == 2 and parts[0], (
            "pointer line is not key, space, value: "
            f"{line!r}"
        )
        pairs.append((parts[0], parts[1]))
    return pairs


def _pointer_candidate(data: bytes, *, digest: str, size: int) -> bool:
    """True when *data* is an empty passthrough or a kv document for *digest*."""
    if size == 0 and data == b"":
        return True
    if not data:
        return False
    try:
        pairs = parse_pointer_kv(data)
    except AssertionError:
        return False
    oid_hex = None
    size_value = None
    for key, value in pairs:
        if key == "oid":
            oid_hex = value.rsplit(":", 1)[-1]
        elif key == "size":
            size_value = value
    return oid_hex == digest and size_value == str(size)


def _kv_block_carrying_digest(data: bytes, *, digest: str, size: int) -> bytes | None:
    """Return a consecutive kv block in *data* that carries *digest* and *size*."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if _POINTER_KV_LINE_RE.match(line):
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    found: list[bytes] = []
    for block in blocks:
        candidate = ("\n".join(block) + "\n").encode("utf-8")
        if _pointer_candidate(candidate, digest=digest, size=size):
            found.append(candidate)
    if not found:
        return None
    assert len(found) == 1, (
        "multiple key/value blocks in the stream carried the digest; "
        "cannot classify a pointer document: "
        f"{found!r}"
    )
    return found[0]


def pointer_document_from_generate(
    result: RunResult, *, digest: str, size: int
) -> bytes:
    """Take the pointer document out of a generate run.

    Generate failure is never mapped to an empty pointer. Stdout is used
    when it is a document for *digest*/*size*; otherwise a consecutive
    key/value block on stderr. Both streams qualifying is unclassified.
    """
    assert result.returncode == 0, (
        "pointer generate failed "
        f"(exit {result.returncode}) argv={list(result.argv)!r}: "
        f"{result.stderr_text}"
    )
    stdout_ok = _pointer_candidate(result.stdout, digest=digest, size=size)
    stderr_block = _kv_block_carrying_digest(
        result.stderr, digest=digest, size=size
    )
    if stdout_ok and stderr_block is not None:
        raise AssertionError(
            "generate wrote a pointer document on both stdout and stderr; "
            "cannot classify which stream is the document"
        )
    if stdout_ok:
        return result.stdout
    if stderr_block is not None:
        return stderr_block
    raise AssertionError(
        "generate did not emit a pointer document carrying the independent "
        f"digest {digest!r} and size {size}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def object_id_field_value(
    pairs: Sequence[tuple[str, str]], *, digest: str
) -> str:
    """Return the object-id field value by shape, not by on-disk key spelling.

    FP-03: hash-method label, colon, lowercase hex matching *digest*.
    Does not pin the object-id key token (that spelling lives in the
    Interface Contract).
    """
    assert digest, "independent digest is empty"
    assert digest == digest.lower(), (
        f"independent digest is not lowercase: {digest!r}"
    )
    assert all(char in "0123456789abcdef" for char in digest), (
        f"independent digest is not hexadecimal: {digest!r}"
    )
    found: list[str] = []
    for _key, value in pairs:
        if ":" not in value:
            continue
        _label, hexpart = value.split(":", 1)
        if hexpart == digest:
            found.append(value)
    assert found, (
        "pointer has no object-id value of hash-method-label, colon, and "
        f"the independent SHA-256 hex {digest!r}; pairs={list(pairs)!r}"
    )
    unique = list(dict.fromkeys(found))
    assert len(unique) == 1, (
        "multiple object-id values matched the independent digest; "
        f"cannot classify the object-id field: {unique!r}"
    )
    value = unique[0]
    _label, hexpart = value.split(":", 1)
    assert hexpart == hexpart.lower(), (
        f"object-id hex digest is not lowercase: {hexpart!r}"
    )
    assert all(char in "0123456789abcdef" for char in hexpart), (
        f"object-id digest is not hexadecimal: {hexpart!r}"
    )
    return value


def require_generated_pointer_shape(
    document: bytes, *, digest: str, size: int
) -> list[tuple[str, str]]:
    """Require generate output under FP-03 line rules without pinning oid.

    Version-first, keys after version sorted, Unix newlines, under 1024,
    object-id value shape (label, colon, independent SHA-256 hex), and a
    size key with the decimal byte length. Does not look up the object-id
    key token.
    """
    if size == 0:
        assert document == b"", (
            "empty content must map to an empty pointer document, "
            f"got {document!r}"
        )
        return []
    assert len(document) < 1024, (
        f"pointer document is not under 1024 bytes: len={len(document)}"
    )
    assert b"\r" not in document, "pointer document is not Unix-newline"
    try:
        document.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"pointer document is not UTF-8: {exc}") from exc
    assert document.endswith(b"\n"), (
        "pointer document is missing a final Unix newline"
    )
    pairs = parse_pointer_kv(document)
    assert pairs, f"hashed pointer document parsed as empty: {document!r}"
    assert pairs[0][0] == "version", (
        "first key is not the version key: "
        f"{pairs[0][0]!r}"
    )
    after = [key for key, _ in pairs[1:]]
    assert after == sorted(after), (
        "keys after version are not sorted ascending: "
        f"{after!r}"
    )
    by_key: dict[str, str] = {}
    for key, value in pairs:
        assert _POINTER_KEY_RE.fullmatch(key), (
            f"pointer key uses characters outside lowercase/digit/dot/hyphen: "
            f"{key!r}"
        )
        assert "\n" not in value and "\r" not in value, (
            f"pointer value contains a CR or LF: {value!r}"
        )
        by_key[key] = value
    object_id_field_value(pairs, digest=digest)
    assert "size" in by_key, (
        f"pointer is missing a size key: keys={list(by_key)!r}"
    )
    assert by_key["size"] == str(size), (
        "size is not the decimal byte length of the file: "
        f"pointer={by_key['size']!r} file={size}"
    )
    return pairs


def pointer_matches_digest_and_size(
    data: bytes, *, digest: str, size: int
) -> bool:
    """True when *data* is empty passthrough or a kv document for *digest*.

    Classifies the object-id field by value shape (hash-method label, colon,
    independent digest), not by on-disk key spelling. Parse failure is not
    a match. An unclassifiable object-id field is a hard failure.
    """
    if size == 0 and data == b"":
        return True
    if not data:
        return False
    try:
        pairs = parse_pointer_kv(data)
    except AssertionError:
        return False
    has_digest = False
    for _key, value in pairs:
        if ":" not in value:
            continue
        _label, hexpart = value.split(":", 1)
        if hexpart == digest:
            has_digest = True
            break
    if not has_digest:
        return False
    object_id_field_value(pairs, digest=digest)
    size_value = None
    for key, value in pairs:
        if key == "size":
            size_value = value
    return size_value == str(size)


def _kv_block_matching_digest_by_shape(
    data: bytes, *, digest: str, size: int
) -> bytes | None:
    """Return a consecutive kv block whose object-id value matches *digest*."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if _POINTER_KV_LINE_RE.match(line):
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    found: list[bytes] = []
    for block in blocks:
        candidate = ("\n".join(block) + "\n").encode("utf-8")
        if pointer_matches_digest_and_size(candidate, digest=digest, size=size):
            found.append(candidate)
    if not found:
        return None
    assert len(found) == 1, (
        "multiple key/value blocks in the stream carried the digest; "
        "cannot classify a pointer document: "
        f"{found!r}"
    )
    return found[0]


def extract_generated_pointer_document(
    result: RunResult, *, digest: str, size: int
) -> bytes:
    """Take the pointer document out of a generate run by object-id value shape.

    Generate failure is never mapped to an empty pointer. Stdout is used
    when it is a document for *digest*/*size*; otherwise a consecutive
    key/value block on stderr. Both streams qualifying is unclassified.
    Does not look up the object-id key token.
    """
    assert result.returncode == 0, (
        "pointer generate failed "
        f"(exit {result.returncode}) argv={list(result.argv)!r}: "
        f"{result.stderr_text}"
    )
    stdout_ok = pointer_matches_digest_and_size(
        result.stdout, digest=digest, size=size
    )
    stderr_block = _kv_block_matching_digest_by_shape(
        result.stderr, digest=digest, size=size
    )
    if stdout_ok and stderr_block is not None:
        raise AssertionError(
            "generate wrote a pointer document on both stdout and stderr; "
            "cannot classify which stream is the document"
        )
    if stdout_ok:
        return result.stdout
    if stderr_block is not None:
        return stderr_block
    raise AssertionError(
        "generate did not emit a pointer document carrying the independent "
        f"digest {digest!r} and size {size}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def object_id_field_key(
    pairs: Sequence[tuple[str, str]], *, digest: str
) -> str:
    """Return the object-id field's on-disk key by value shape, not spelling.

    FP-03: the field whose value is hash-method label, colon, and *digest*.
    Does not pin the key token (that spelling lives in the Interface Contract).
    """
    value = object_id_field_value(pairs, digest=digest)
    keys = [key for key, val in pairs if val == value]
    unique = list(dict.fromkeys(keys))
    assert unique, (
        "object-id value was classified but no key carries it; "
        f"pairs={list(pairs)!r}"
    )
    assert len(unique) == 1, (
        "multiple keys carried the object-id value; cannot classify "
        f"the object-id field: {unique!r}"
    )
    return unique[0]


def reorder_required_size_before_object_id(
    document: bytes, *, digest: str
) -> bytes:
    """Rebuild a pointer with size before the object-id field.

    Finds the object-id field by value shape. Does not pin its key spelling.
    Required-key order becomes version, size, extras, object-id — invalid
    under FP-03, not merely non-canonical.
    """
    pairs = parse_pointer_kv(document)
    object_id_key = object_id_field_key(pairs, digest=digest)
    by_key = {key: value for key, value in pairs}
    assert "version" in by_key and "size" in by_key, (
        f"pointer is missing version or size: keys={list(by_key)!r}"
    )
    extras = [
        (key, value)
        for key, value in pairs
        if key not in ("version", object_id_key, "size")
    ]
    return join_pointer_kv(
        [
            ("version", by_key["version"]),
            ("size", by_key["size"]),
            *extras,
            (object_id_key, by_key[object_id_key]),
        ]
    )


def well_formed_oversize_pointer(document: bytes, *, digest: str) -> bytes:
    """Rebuild *document* as a well-formed pointer that exceeds 1024 bytes.

    Keeps version, object-id (by value shape), and size. Pads with one
    protocol extension-line key whose value is that same object-id
    field, so the document remains parseable key/value lines with
    required keys and sorted keys after version; only the size limit
    is violated. Distinct from an oversize non-pointer blob. Does not
    pin the object-id key spelling.
    """
    pairs = parse_pointer_kv(document)
    assert pairs and pairs[0][0] == "version", (
        f"generated pointer is missing a leading version key: {pairs!r}"
    )
    object_id_key = object_id_field_key(pairs, digest=digest)
    object_id_value = object_id_field_value(pairs, digest=digest)
    by_key = {key: value for key, value in pairs}
    assert "version" in by_key and "size" in by_key, (
        f"pointer is missing version or size: keys={list(by_key)!r}"
    )
    extras = [
        (key, value)
        for key, value in pairs
        if key not in ("version", object_id_key, "size")
    ]
    used_priorities: set[int] = set()
    for key, _value in extras:
        parts = key.split("-", 2)
        if len(parts) == 3 and parts[0] == "ext" and parts[1].isdigit():
            used_priorities.add(int(parts[1]))
    priority = 0
    while priority in used_priorities:
        priority += 1
        assert priority <= 9, (
            "no free extension-line priority for an oversize pad: "
            f"{sorted(used_priorities)!r}"
        )
    pad_prefix = f"ext-{priority}-p{token()}"
    assert _POINTER_KEY_RE.fullmatch(pad_prefix), (
        f"oversize pad key prefix is not a pointer key: {pad_prefix!r}"
    )
    rest_core = [
        *extras,
        (object_id_key, object_id_value),
        ("size", by_key["size"]),
    ]
    # The check/smudge parsers look at at most 1024 bytes. Padding the
    # extension key itself (not a trailing extra byte) keeps oid/size
    # past that window, so a well-formed oversize document is rejected
    # as a pointer rather than parsed as a truncated canonical prefix.
    pad_key = pad_prefix + ("x" * 1024)
    assert _POINTER_KEY_RE.fullmatch(pad_key), (
        f"oversize pad key is not a pointer key: {pad_key!r}"
    )
    rest = sorted(
        [*rest_core, (pad_key, object_id_value)],
        key=lambda item: item[0],
    )
    oversize = join_pointer_kv([("version", by_key["version"]), *rest])
    assert len(oversize) > 1024, (
        "well-formed oversize pointer did not exceed 1024 bytes: "
        f"len={len(oversize)}"
    )
    parsed = parse_pointer_kv(oversize)
    assert parsed and parsed[0][0] == "version"
    after = [key for key, _ in parsed[1:]]
    assert after == sorted(after), (
        "well-formed oversize pointer keys after version are not sorted: "
        f"{after!r}"
    )
    object_id_field_value(parsed, digest=digest)
    parsed_keys = {key for key, _ in parsed}
    assert "size" in parsed_keys, (
        f"well-formed oversize pointer dropped size: keys={parsed_keys!r}"
    )
    return oversize


def require_canonical_pointer_shape(
    document: bytes, *, digest: str, size: int
) -> list[tuple[str, str]]:
    """Require a UTF-8 key/value pointer under the FP-03 line and size rules.

    Does not pin the version-identifier string or the hash-method label.
    Empty content is the empty document, not a hashed body.
    """
    if size == 0:
        assert document == b"", (
            "empty content must map to an empty pointer document, "
            f"got {document!r}"
        )
        return []
    assert len(document) < 1024, (
        f"pointer document is not under 1024 bytes: len={len(document)}"
    )
    assert b"\r" not in document, "pointer document is not Unix-newline"
    try:
        document.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"pointer document is not UTF-8: {exc}") from exc
    assert document.endswith(b"\n"), (
        "pointer document is missing a final Unix newline"
    )
    pairs = parse_pointer_kv(document)
    assert pairs, f"hashed pointer document parsed as empty: {document!r}"
    assert pairs[0][0] == "version", (
        "first key is not the version key: "
        f"{pairs[0][0]!r}"
    )
    after = [key for key, _ in pairs[1:]]
    assert after == sorted(after), (
        "keys after version are not sorted ascending: "
        f"{after!r}"
    )
    by_key: dict[str, str] = {}
    for key, value in pairs:
        assert _POINTER_KEY_RE.fullmatch(key), (
            f"pointer key uses characters outside lowercase/digit/dot/hyphen: "
            f"{key!r}"
        )
        assert "\n" not in value and "\r" not in value, (
            f"pointer value contains a CR or LF: {value!r}"
        )
        by_key[key] = value
    assert "oid" in by_key and "size" in by_key, (
        f"pointer is missing oid or size: keys={list(by_key)!r}"
    )
    oid_value = by_key["oid"]
    assert ":" in oid_value, (
        "oid value is not hash-method-label, colon, hex digest: "
        f"{oid_value!r}"
    )
    _label, hexpart = oid_value.split(":", 1)
    assert hexpart == digest, (
        "oid hex digest does not match independent SHA-256 of the file: "
        f"oid={hexpart!r} independent={digest!r}"
    )
    assert hexpart == hexpart.lower(), (
        f"oid hex digest is not lowercase: {hexpart!r}"
    )
    assert all(char in "0123456789abcdef" for char in hexpart), (
        f"oid digest is not hexadecimal: {hexpart!r}"
    )
    assert by_key["size"] == str(size), (
        "size is not the decimal byte length of the file: "
        f"pointer={by_key['size']!r} file={size}"
    )
    return pairs


def run_pointer(
    ws: Workspace,
    argv: Sequence[str],
    *,
    stdin: bytes | str | None = None,
    via_git: bool = True,
) -> RunResult:
    """Run the pointer plumbing subcommand."""
    args = ["pointer", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, stdin=stdin)
    return ws.invoke(args, stdin=stdin)


def check_pointer(
    ws: Workspace,
    document: bytes,
    *,
    strict: bool = False,
    via: str = "file",
) -> RunResult:
    """Run pointer check on *document* via ``--file=`` or ``--stdin``."""
    argv: list[str] = ["--check"]
    if strict:
        argv.append("--strict")
    if via == "file":
        rel = f"chk_{token()}"
        ws.write(rel, document)
        argv.append(f"--file={rel}")
        return run_pointer(ws, argv)
    if via == "stdin":
        argv.append("--stdin")
        return run_pointer(ws, argv, stdin=document)
    raise AssertionError(f"check_pointer via must be 'file' or 'stdin', got {via!r}")


def require_pointer_check_ok(result: RunResult) -> RunResult:
    """Require pointer check success."""
    return require_success(result)


def require_pointer_invalid(
    result: RunResult, *, unlike: RunResult
) -> RunResult:
    """Require *result* is a refused pointer, distinguishable from *unlike*."""
    assert unlike.returncode == 0, (
        "live baseline check must succeed before an invalid pointer can "
        f"be measured, got exit {unlike.returncode}: {unlike.stderr_text}"
    )
    assert result.returncode != 0, (
        "expected a non-zero check status for an invalid pointer, "
        f"got {result.returncode}; stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert (result.returncode, result.stdout, result.stderr) != (
        unlike.returncode,
        unlike.stdout,
        unlike.stderr,
    ), "invalid-pointer check was not distinguishable from a successful check"
    return result


def require_invalid_check_invocation(
    clean: RunResult, dirty: RunResult
) -> RunResult:
    """Require *dirty* is an invalid check invocation relative to *clean*.

    FP-03 names missing-source, both-sources, check-plus-compare-pointer,
    and strict-plus-non-strict as invalid. The live baseline (*clean*) must
    succeed. The dirty run must exit non-zero and be distinguishable from
    that success. Does not require a message on stderr.
    """
    assert clean.returncode == 0, (
        "live baseline check must succeed before an invalid invocation "
        f"can be measured, got exit {clean.returncode}: {clean.stderr_text}"
    )
    assert dirty.returncode != 0, (
        "expected a non-zero exit for an invalid check invocation, "
        f"got {dirty.returncode}; stdout={dirty.stdout_text!r} "
        f"stderr={dirty.stderr_text!r}"
    )
    assert (dirty.returncode, dirty.stdout, dirty.stderr) != (
        clean.returncode,
        clean.stdout,
        clean.stderr,
    ), (
        "invalid check invocation was not distinguishable from the "
        "successful check"
    )
    return dirty


def require_valid_not_canonical(
    result: RunResult,
    *,
    unlike_ok: RunResult,
    unlike_invalid: RunResult,
) -> RunResult:
    """Require a valid-but-not-canonical strict failure, unlike invalid."""
    assert unlike_ok.returncode == 0, (
        "live baseline strict check of a canonical pointer must succeed, "
        f"got exit {unlike_ok.returncode}: {unlike_ok.stderr_text}"
    )
    assert result.returncode != 0, (
        "expected a non-zero strict status for a valid-but-not-canonical "
        f"pointer, got {result.returncode}; stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert (result.returncode, result.stdout, result.stderr) != (
        unlike_ok.returncode,
        unlike_ok.stdout,
        unlike_ok.stderr,
    ), "valid-but-not-canonical was not distinguishable from canonical success"
    assert (result.returncode, result.stdout, result.stderr) != (
        unlike_invalid.returncode,
        unlike_invalid.stdout,
        unlike_invalid.stderr,
    ), (
        "valid-but-not-canonical strict failure was not distinguishable "
        "from an invalid-pointer failure"
    )
    return result


def compare_pointer(
    ws: Workspace,
    file_path: str | Path,
    other: bytes | str | Path,
    *,
    via: str = "file",
) -> RunResult:
    """Compare the pointer generated from *file_path* to *other*."""
    file_arg = f"--file={file_path}"
    if via == "file":
        if isinstance(other, bytes):
            rel = f"cmp_{token()}"
            ws.write(rel, other)
            other_arg = rel
        else:
            other_arg = str(other)
        return run_pointer(ws, [file_arg, f"--pointer={other_arg}"])
    if via == "stdin":
        if isinstance(other, bytes):
            data = other
        else:
            data = Path(other).read_bytes()
        return run_pointer(ws, [file_arg, "--stdin"], stdin=data)
    raise AssertionError(
        f"compare_pointer via must be 'file' or 'stdin', got {via!r}"
    )


def compare_class_observation(
    result: RunResult, *, strip_tokens: Sequence[str]
) -> tuple[int, str]:
    """Return ``(returncode, covariate-stripped visible output)``.

    Strips caller tokens (paths, payloads, pointer documents, digests),
    ``--file=`` / ``--pointer=`` argv paths, whole-word decimal sizes, and
    Git blob hex. Does not pin message text.
    """
    visible = caller_visible(result)
    long_tokens: list[str] = []
    numeric: list[str] = []
    for arg in result.argv:
        text = str(arg)
        for prefix in ("--file=", "--pointer="):
            if text.startswith(prefix):
                path = text[len(prefix):]
                if path:
                    long_tokens.append(path)
                    long_tokens.append(Path(path).name)
    for item in strip_tokens:
        if not item:
            continue
        if str(item).isdigit():
            numeric.append(str(item))
        else:
            long_tokens.append(str(item))
    remainder = _strip_unrelated_tokens(visible, long_tokens)
    for item in sorted(numeric, key=len, reverse=True):
        remainder = _strip_whole_word(remainder, item)
    remainder = _GIT_BLOB_HEX_RE.sub(" ", remainder)
    carrier = " ".join(remainder.split())
    return (result.returncode, carrier)


def require_shared_class(
    obs_a: tuple[int, str], obs_b: tuple[int, str]
) -> tuple[int, str]:
    """Require two compare observations to share one outcome class."""
    assert obs_a == obs_b, (
        "compare observations did not share a class after stripping "
        f"input-byte covariates: {obs_a!r} vs {obs_b!r}"
    )
    return obs_a


def require_distinct_classes(*observations: tuple[int, str]) -> None:
    """Require compare outcome classes to be mutually distinguishable."""
    assert len(observations) >= 2, "need at least two classes to distinguish"
    unique = set(observations)
    assert len(unique) == len(observations), (
        "compare outcome classes were not mutually distinguishable after "
        f"stripping input-byte covariates: {observations!r}"
    )


def require_valid_not_canonical_stripped(
    result: RunResult,
    *,
    unlike_ok: RunResult,
    unlike_invalid: RunResult,
    input_documents: Sequence[bytes],
) -> RunResult:
    """Require a valid-but-not-canonical strict failure after covariate strip.

    Live baseline *unlike_ok* must succeed. *result* must exit non-zero.
    After stripping file-path and input-byte covariates, *result* must
    still differ from both canonical strict success and an invalid-pointer
    strict failure. Does not pin exit codes or message text.
    """
    assert unlike_ok.returncode == 0, (
        "live baseline strict check of a canonical pointer must succeed, "
        f"got exit {unlike_ok.returncode}: {unlike_ok.stderr_text}"
    )
    assert unlike_invalid.returncode != 0, (
        "invalid-pointer strict control must fail, "
        f"got exit {unlike_invalid.returncode}: "
        f"{unlike_invalid.stderr_text}"
    )
    assert result.returncode != 0, (
        "expected a non-zero strict status for a valid-but-not-canonical "
        f"pointer, got {result.returncode}; stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    strip: list[str] = []
    for raw in input_documents:
        try:
            strip.append(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise AssertionError(
                "input document is not UTF-8; cannot strip it as an "
                f"input-byte covariate: {exc}"
            ) from exc
    obs = compare_class_observation(result, strip_tokens=strip)
    obs_ok = compare_class_observation(unlike_ok, strip_tokens=strip)
    obs_invalid = compare_class_observation(
        unlike_invalid, strip_tokens=strip
    )
    print(
        f"vnc_stripped={obs!r} ok_stripped={obs_ok!r} "
        f"invalid_stripped={obs_invalid!r}"
    )
    assert obs != obs_ok, (
        "valid-but-not-canonical was not distinguishable from canonical "
        "success after stripping file-path and input-byte covariates: "
        f"{obs!r}"
    )
    assert obs != obs_invalid, (
        "valid-but-not-canonical strict failure was not distinguishable "
        "from an invalid-pointer failure after stripping file-path and "
        f"input-byte covariates: {obs!r} vs {obs_invalid!r}"
    )
    return result


def smudge_bytes(ws: Workspace, document: bytes) -> RunResult:
    """Run filter smudge on *document* bytes via stdin."""
    return ws.invoke_via_git(["smudge"], stdin=document)


def require_smudge_passthrough(
    result: RunResult, document: bytes
) -> RunResult:
    """Require smudge copied *document* through as ordinary blob bytes."""
    assert result.stdout == document, (
        "smudge did not pass structural-invalid bytes through unchanged: "
        f"stdout={result.stdout!r} input={document!r} "
        f"exit={result.returncode}"
    )
    return result


def require_smudge_recognizes(
    result: RunResult, document: bytes
) -> RunResult:
    """Require smudge did not successfully copy a pointer through as a blob."""
    passthrough = result.returncode == 0 and result.stdout == document
    assert not passthrough, (
        "smudge treated a pointer document as ordinary-blob passthrough "
        f"(exit 0 and stdout equaled the input); input={document!r}"
    )
    return result


def assert_smudge_recognizes(
    result: RunResult, document: bytes
) -> RunResult:
    """Require smudge did not successfully copy a pointer through as a blob.

    Filter smudge recognition (FP-03): a valid pointer, including
    valid-but-not-canonical carriage-return line endings, must not be
    copied through as ordinary blob bytes on a successful exit.
    """
    passthrough = result.returncode == 0 and result.stdout == document
    assert not passthrough, (
        "smudge treated a pointer document as ordinary-blob passthrough "
        f"(exit 0 and stdout equaled the input); input={document!r}"
    )
    return result


def require_smudge_recognizes_as_pointer(
    result: RunResult,
    document: bytes,
    *,
    unlike_passthrough: RunResult,
    passthrough_input: bytes,
    unlike_independent_failure: RunResult,
) -> RunResult:
    """Require filter smudge recognized *document* as a pointer.

    The only accepted green path is distinguishable both from successful
    copy-through of *document* and from a smudge that fails independently
    of whether the input is a pointer. The live baseline
    *unlike_passthrough* must copy *passthrough_input* through as ordinary
    blob bytes. Does not pin exit codes or message text.
    """
    require_smudge_passthrough(unlike_passthrough, passthrough_input)
    assert unlike_independent_failure.returncode != 0, (
        "independent-failure control must fail independently of whether "
        "the input is a pointer; got success "
        f"exit={unlike_independent_failure.returncode} "
        f"stdout={unlike_independent_failure.stdout!r} "
        f"stderr={unlike_independent_failure.stderr!r}"
    )
    copy_through = result.returncode == 0 and result.stdout == document
    assert not copy_through, (
        "smudge treated a pointer document as ordinary-blob passthrough "
        f"(exit 0 and stdout equaled the input); input={document!r}"
    )
    strip: list[str] = []
    for raw in (document, passthrough_input):
        strip.append(raw.decode("utf-8"))
    obs = compare_class_observation(result, strip_tokens=strip)
    obs_pass = compare_class_observation(
        unlike_passthrough, strip_tokens=strip
    )
    obs_ind = compare_class_observation(
        unlike_independent_failure, strip_tokens=strip
    )
    assert obs != obs_pass, (
        "smudge of a pointer was not distinguishable from ordinary-blob "
        f"passthrough after stripping input bytes: {obs!r}"
    )
    assert obs != obs_ind, (
        "smudge of a pointer was not distinguishable from a smudge that "
        "fails independently of whether the input is a pointer: "
        f"{obs!r} vs {obs_ind!r}"
    )
    return result


def assert_smudge_recognizes_as_pointer(
    result: RunResult,
    document: bytes,
    *,
    unlike_passthrough: RunResult,
    passthrough_input: bytes,
    unlike_independent_failure: RunResult,
) -> RunResult:
    """Require filter smudge recognized *document* as a pointer.

    Same contract as ``require_smudge_recognizes_as_pointer``. The name
    is the verdict the suite-bailout audit can see: a smudge that always
    fails, or that always writes unrelated bytes, is not recognition.
    """
    return require_smudge_recognizes_as_pointer(
        result,
        document,
        unlike_passthrough=unlike_passthrough,
        passthrough_input=passthrough_input,
        unlike_independent_failure=unlike_independent_failure,
    )


def _utf8_covariate_tokens(*documents: bytes) -> list[str]:
    """Decode input documents for covariate stripping. Decode failure is not absence."""
    tokens: list[str] = []
    for raw in documents:
        try:
            tokens.append(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise AssertionError(
                "input document is not UTF-8; cannot strip it as an "
                f"input-byte covariate: {exc}"
            ) from exc
    return tokens


def require_smudge_recognized_unlike_independent_failure(
    result: RunResult,
    document: bytes,
    *,
    unlike_independent_failure: RunResult,
) -> RunResult:
    """Require filter smudge recognized *document* as a pointer.

    Not successful copy-through of *document*, and distinguishable from
    a smudge that fails independently of whether the input is a pointer.
    Does not require a copy-through baseline. Does not pin exit codes
    or message text.
    """
    require_smudge_recognizes(result, document)
    assert unlike_independent_failure.returncode != 0, (
        "independent-failure control must fail independently of whether "
        "the input is a pointer; got success "
        f"exit={unlike_independent_failure.returncode} "
        f"stdout={unlike_independent_failure.stdout!r} "
        f"stderr={unlike_independent_failure.stderr!r}"
    )
    strip = _utf8_covariate_tokens(document)
    obs = compare_class_observation(result, strip_tokens=strip)
    obs_ind = compare_class_observation(
        unlike_independent_failure, strip_tokens=strip
    )
    print(f"smudge_recognized={obs!r} independent_failure={obs_ind!r}")
    assert obs != obs_ind, (
        "smudge of a pointer was not distinguishable from a smudge that "
        "fails independently of whether the input is a pointer: "
        f"{obs!r} vs {obs_ind!r}"
    )
    return result


def require_smudge_not_recognized_as_pointer(
    result: RunResult,
    document: bytes,
    *,
    unlike_recognized: RunResult,
    recognized_input: bytes,
) -> RunResult:
    """Require filter smudge did not treat *document* as a pointer.

    FP-03: structurally invalid forms are rejected as pointers by
    filter smudge recognition. The live baseline *unlike_recognized*
    must itself be recognition of *recognized_input* (not successful
    copy-through of that pointer). After stripping input-byte
    covariates, *result* must remain distinguishable from that
    recognition. Does not require stdout to equal the unrecognized
    input (copy-through of non-pointers is FP-05). Does not pin exit
    codes or message text.
    """
    require_smudge_recognizes(unlike_recognized, recognized_input)
    strip = _utf8_covariate_tokens(document, recognized_input)
    obs = compare_class_observation(result, strip_tokens=strip)
    obs_rec = compare_class_observation(
        unlike_recognized, strip_tokens=strip
    )
    print(f"smudge_unrecognized={obs!r} recognized={obs_rec!r}")
    assert obs != obs_rec, (
        "smudge did not reject the input as a pointer: after stripping "
        "input bytes, the outcome was not distinguishable from "
        f"valid-pointer recognition: {obs!r} vs {obs_rec!r}"
    )
    return result


def stage_mode(ws: Workspace, path: str | Path) -> str:
    """Return the index mode from ``git ls-files --stage``. Failure is not absence."""
    rel = str(path)
    result = ws.git(["ls-files", "--stage", "--", rel])
    assert result.returncode == 0, (
        f"git ls-files --stage {rel!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    line = result.stdout_text.strip()
    assert line, (
        f"git ls-files --stage {rel!r} produced no staging record"
    )
    mode = line.split()[0]
    assert mode, f"staging record had no mode: {line!r}"
    return mode


def configure_lfs_clean_filter(ws: Workspace) -> None:
    """Setup: make subsequent ``git add`` use this build's clean filter.

    Disables the process filter so Git takes the clean path. Not an
    install/uninstall oracle.
    """
    installed = ws.invoke_via_git(["install", "--local"])
    require_success(installed)
    unset = ws.git(["config", "--local", "--unset", "filter.lfs.process"])
    assert unset.returncode == 0, (
        "failed to disable the process filter so git add uses clean "
        f"(exit {unset.returncode}): {unset.stderr_text}"
    )


def register_byte_transform_extension(ws: Workspace) -> str:
    """Setup: register a clean/smudge extension that actually changes bytes.

    Name and priority are runtime-generated. Returns the extension name
    for diagnostics; callers must not pin pointer key spelling from it.
    """
    name = f"xf{token()}"
    transform = "tr '[:lower:][:upper:]' '[:upper:][:lower:]'"
    require_git_config_set(
        ws, f"lfs.extension.{name}.clean", transform, local=True
    )
    require_git_config_set(
        ws, f"lfs.extension.{name}.smudge", transform, local=True
    )
    require_git_config_set(
        ws, f"lfs.extension.{name}.priority", "0", local=True
    )
    return name


# ---------------------------------------------------------------------------
# F04: track / untrack
# ---------------------------------------------------------------------------

_GIT_ATTR_UNSPECIFIED = "unspecified"
_GIT_ATTR_UNSET = "unset"
_GIT_ATTR_SET = "set"
_LFS_FILTER_VALUE = "lfs"


def run_track(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the track porcelain with *argv* after the subcommand name."""
    args = ["track", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def run_untrack(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
) -> RunResult:
    """Run the untrack porcelain with *argv* after the subcommand name."""
    args = ["untrack", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd)
    return ws.invoke(args, cwd=cwd)


def gitattributes_path(rel: str = ".gitattributes") -> str:
    """Return the repository-relative attributes path used by these tests."""
    assert rel, "gitattributes relative path must be non-empty"
    return rel


def read_gitattributes(
    ws: Workspace, rel: str = ".gitattributes"
) -> str:
    """Read the attributes file as text. Missing is FileNotFoundError, never empty."""
    return ws.read(gitattributes_path(rel))


def require_gitattributes_absent(
    ws: Workspace, rel: str = ".gitattributes"
) -> None:
    """Require that the attributes file is not present as a regular file."""
    path = gitattributes_path(rel)
    try:
        data = ws.read_bytes(path)
    except FileNotFoundError:
        return
    raise AssertionError(
        f"expected {path!r} to be absent, found {data!r}"
    )


def gitattributes_bytes_or_missing(
    ws: Workspace, rel: str = ".gitattributes"
) -> bytes | None:
    """Return attributes bytes, or None only when the file is missing."""
    path = gitattributes_path(rel)
    try:
        return ws.read_bytes(path)
    except FileNotFoundError:
        return None


def git_check_attr(
    ws: Workspace, path: str, names: Sequence[str]
) -> dict[str, str]:
    """Return Git attribute values for *path* via ``git check-attr -z``.

    A non-zero Git status is a hard failure, never an empty mapping.
    """
    assert names, "git_check_attr requires at least one attribute name"
    result = ws.git(["check-attr", "-z", *[str(n) for n in names], "--", path])
    assert result.returncode == 0, (
        f"git check-attr {list(names)!r} -- {path!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    parts = result.stdout.split(b"\0")
    if parts and parts[-1] == b"":
        parts = parts[:-1]
    assert len(parts) % 3 == 0, (
        "git check-attr -z output is not path/attr/value triples: "
        f"{result.stdout!r}"
    )
    values: dict[str, str] = {}
    for index in range(0, len(parts), 3):
        attr = parts[index + 1].decode("utf-8")
        value = parts[index + 2].decode("utf-8")
        values[attr] = value
    for name in names:
        assert name in values, (
            f"git check-attr did not report {name!r} for {path!r}: "
            f"{values!r} raw={result.stdout!r}"
        )
    return values


def require_lfs_enable_roles(ws: Workspace, path: str) -> dict[str, str]:
    """Require filter/diff/merge = lfs and text disabled or unspecified.

    Does not pin ``-text`` spelling in the attributes file. Does not
    assert lockable; callers that need that contrast use
    ``require_lockable_set`` / ``require_lockable_unset``.
    """
    values = git_check_attr(ws, path, ["filter", "diff", "merge", "text"])
    for role in ("filter", "diff", "merge"):
        assert values[role] == _LFS_FILTER_VALUE, (
            f"{role} for {path!r} is {values[role]!r}, not lfs"
        )
    assert values["text"] in (_GIT_ATTR_UNSET, _GIT_ATTR_UNSPECIFIED), (
        f"text for {path!r} is not disabled/unspecified: {values['text']!r}"
    )
    assert values["text"] != _LFS_FILTER_VALUE, (
        f"text for {path!r} is lfs; ordinary track disables text conversion"
    )
    return values


def require_text_conversion_disabled(
    ws: Workspace, path: str
) -> dict[str, str]:
    """Require Git text conversion is disabled for *path*.

    Observes ``git check-attr text``. Git reports unset when the text
    attribute is defined as false (conversion off). Unspecified is
    Git's default, not a disable. Set, or any assigned value including
    lfs, is not a disable. Does not pin attributes-file spelling.
    """
    values = git_check_attr(ws, path, ["text"])
    observed = values["text"]
    assert observed == _GIT_ATTR_UNSET, (
        "Git text conversion is not disabled for "
        f"{path!r}: text={observed!r}"
    )
    return values


def require_lockable_set(ws: Workspace, path: str) -> dict[str, str]:
    """Require lockable is set for *path*."""
    values = git_check_attr(ws, path, ["lockable"])
    assert values["lockable"] == _GIT_ATTR_SET, (
        f"lockable for {path!r} is not set: {values['lockable']!r}"
    )
    return values


def require_lockable_unset(ws: Workspace, path: str) -> dict[str, str]:
    """Require lockable is unspecified or unset for *path*."""
    values = git_check_attr(ws, path, ["lockable"])
    assert values["lockable"] in (_GIT_ATTR_UNSPECIFIED, _GIT_ATTR_UNSET), (
        f"lockable for {path!r} is not unset/unspecified: {values['lockable']!r}"
    )
    return values


def require_pattern_text_in_attributes(
    ws: Workspace, pattern: str, rel: str = ".gitattributes"
) -> str:
    """Require the given pattern text appears in the attributes file."""
    text = read_gitattributes(ws, rel)
    assert pattern in text, (
        f"attributes file does not contain pattern text {pattern!r}: {text!r}"
    )
    return text


def commit_ordinary_blob(
    ws: Workspace, rel: str, content: str | bytes
) -> str:
    """Setup: add and commit *rel* as an ordinary Git blob. Not an LFS path."""
    ws.write(rel, content)
    added = ws.git(["add", "--", rel])
    assert added.returncode == 0, (
        f"git add {rel!r} failed (exit {added.returncode}): {added.stderr_text}"
    )
    committed = ws.git(["commit", "-m", f"add {rel}"])
    assert committed.returncode == 0, (
        f"git commit {rel!r} failed (exit {committed.returncode}): "
        f"{committed.stderr_text}"
    )
    return rel


def head_oid(ws: Workspace) -> str:
    """Return ``git rev-parse HEAD``. Failure is not absence."""
    result = ws.git(["rev-parse", "HEAD"])
    assert result.returncode == 0, (
        f"git rev-parse HEAD failed (exit {result.returncode}): "
        f"{result.stderr_text}"
    )
    oid = result.stdout_text.strip()
    assert oid, f"git rev-parse HEAD produced no oid: {result.stdout!r}"
    return oid


def porcelain_paths(ws: Workspace) -> list[str]:
    """Return paths from ``git status --porcelain``. Failure is not absence."""
    result = ws.git(["status", "--porcelain", "-uall"])
    assert result.returncode == 0, (
        f"git status --porcelain failed (exit {result.returncode}): "
        f"{result.stderr_text}"
    )
    paths: list[str] = []
    for line in result.stdout_text.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) >= 4 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        assert rest, f"porcelain line had no path: {line!r}"
        paths.append(rest)
    return paths


def listing_visible(result: RunResult) -> str:
    """Caller-visible listing text. Does not pin stdout vs stderr."""
    return caller_visible(result)


def require_visible_contains(result: RunResult, token: str) -> str:
    """Require *token* appears in caller-visible output."""
    text = listing_visible(result)
    assert token in text, (
        f"caller-visible output does not contain {token!r}: {text!r}"
    )
    return text


def assert_visible_contains(result: RunResult, token: str) -> str:
    """Require *token* appears in caller-visible output.

    Same contract as ``require_visible_contains``. The name is the
    verdict the suite-bailout audit can see: a listing that omits the
    path has not named it.
    """
    return require_visible_contains(result, token)


def require_visible_omits(result: RunResult, token: str) -> str:
    """Require *token* does not appear in caller-visible output."""
    text = listing_visible(result)
    assert token not in text, (
        f"caller-visible output unexpectedly contains {token!r}: {text!r}"
    )
    return text


def extract_json_listing(result: RunResult) -> object:
    """Extract one parseable JSON value from caller-visible output.

    Tries the whole text first, then locates a parseable object or array
    in the text. Failure to extract JSON is a hard failure, never an
    empty list. Does not require JSON to occupy all of stdout. Does not
    pin field names.
    """
    text = listing_visible(result)
    decoder = json.JSONDecoder()
    stripped = text.lstrip()
    if stripped:
        try:
            value, _consumed = decoder.raw_decode(stripped)
            return value
        except json.JSONDecodeError:
            pass
    found: list[object] = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        found.append(value)
    assert found, (
        "caller-visible output contained no parseable JSON listing: "
        f"{text!r}"
    )
    for value in found:
        if isinstance(value, (dict, list)):
            return value
    return found[0]


def json_walk_keys_and_strings(obj: object) -> list[str]:
    """Collect object keys and string values recursively.

    Does not walk only string values and miss a pattern used as a key.
    """
    collected: list[str] = []

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                collected.append(str(key))
                _walk(inner)
            return
        if isinstance(value, list):
            for inner in value:
                _walk(inner)
            return
        if isinstance(value, str):
            collected.append(value)

    _walk(obj)
    return collected


def write_excluded_filter_line(
    ws: Workspace,
    pattern: str,
    *,
    form: str = "negate",
    rel: str = ".gitattributes",
) -> str:
    """Fixture: append a Git filter negation or unset line. Not a product entry."""
    if form == "negate":
        line = f"{pattern} -filter\n"
    elif form == "unset":
        line = f"{pattern} filter=\n"
    else:
        raise AssertionError(
            f"write_excluded_filter_line form must be 'negate' or 'unset', "
            f"got {form!r}"
        )
    path = gitattributes_path(rel)
    try:
        existing = ws.read_bytes(path)
    except FileNotFoundError:
        existing = b""
    ws.write(path, existing + line.encode("utf-8"))
    return line


def require_invalid_unlike_success(
    clean: RunResult, dirty: RunResult
) -> RunResult:
    """Require *dirty* is an invalid invocation relative to successful *clean*.

    The live baseline (*clean*) must succeed. The dirty run must exit
    non-zero and be distinguishable from that success. Does not require
    a message on stderr. Does not pin an exit code or message text.
    """
    assert clean.returncode == 0, (
        "live baseline must succeed before an invalid invocation "
        f"can be measured, got exit {clean.returncode}: {clean.stderr_text}"
    )
    assert dirty.returncode != 0, (
        "expected a non-zero exit for an invalid invocation, "
        f"got {dirty.returncode}; stdout={dirty.stdout_text!r} "
        f"stderr={dirty.stderr_text!r}"
    )
    assert (dirty.returncode, dirty.stdout, dirty.stderr) != (
        clean.returncode,
        clean.stdout,
        clean.stderr,
    ), (
        "invalid invocation was not distinguishable from the successful run"
    )
    return dirty


def assert_invalid_unlike_success(
    clean: RunResult, dirty: RunResult
) -> RunResult:
    """Require *dirty* is invalid relative to successful *clean*.

    Same contract as ``require_invalid_unlike_success``. The name is the
    verdict the suite-bailout audit can see: an all-mode combination that
    still succeeds is not a refusal.
    """
    return require_invalid_unlike_success(clean, dirty)


# ---------------------------------------------------------------------------
# F05: clean / smudge / filter-process / local object store
# ---------------------------------------------------------------------------


def git_dir(ws: Workspace) -> Path:
    """Return the repository Git directory. A failed rev-parse is not absence."""
    result = ws.git(["rev-parse", "--git-dir"])
    assert result.returncode == 0, (
        "git rev-parse --git-dir failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    raw = result.stdout_text.strip()
    assert raw, "git rev-parse --git-dir produced no path"
    path = Path(raw)
    if not path.is_absolute():
        path = (ws.path / path).resolve()
    else:
        path = path.resolve()
    return path


def default_lfs_store_root(ws: Workspace) -> Path:
    """Default local object-store root: Git directory / ``lfs``."""
    return git_dir(ws) / "lfs"


def sharded_object_rel(oid: str) -> str:
    """Return ``objects/<aa>/<bb>/<oid>`` for an independent hex object id."""
    assert len(oid) >= 4, f"object id is too short to shard: {oid!r}"
    return f"objects/{oid[:2]}/{oid[2:4]}/{oid}"


def require_object_bytes(
    store_root: Path, oid: str, content: bytes
) -> Path:
    """Require the sharded object file exists and equals *content*.

    A missing file is ``object missing at …``, never an empty body.
    An unreadable path is a hard failure.
    """
    path = Path(store_root) / sharded_object_rel(oid)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise AssertionError(f"object missing at {path}") from None
    except OSError as exc:
        raise AssertionError(f"cannot read object at {path}: {exc}") from exc
    assert data == content, (
        f"object at {path} is not the original content "
        f"(got {len(data)} bytes, expected {len(content)})"
    )
    return path


def require_object_absent(store_root: Path, oid: str) -> None:
    """Require the sharded object path does not exist.

    An unreadable parent directory is a hard failure, not absence.
    """
    path = Path(store_root) / sharded_object_rel(oid)
    parent = path.parent
    try:
        parent_exists = parent.exists()
    except OSError as exc:
        raise AssertionError(
            f"cannot stat object parent {parent}: {exc}"
        ) from exc
    if parent_exists:
        try:
            os.listdir(parent)
        except OSError as exc:
            raise AssertionError(
                f"cannot read object parent {parent}: {exc}"
            ) from exc
    try:
        exists = path.exists()
    except OSError as exc:
        raise AssertionError(f"cannot stat object path {path}: {exc}") from exc
    assert not exists, f"object unexpectedly present at {path}"


def index_blob(ws: Workspace, relpath: str) -> bytes:
    """Return ``git cat-file blob :relpath``. Non-zero is not an empty blob."""
    result = ws.git(["cat-file", "blob", f":{relpath}"])
    assert result.returncode == 0, (
        f"git cat-file blob :{relpath} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result.stdout


def clean_bytes(
    ws: Workspace, data: bytes, *, via_git: bool = True
) -> RunResult:
    """Run clean with *data* on stdin."""
    if via_git:
        return ws.invoke_via_git(["clean"], stdin=data)
    return ws.invoke(["clean"], stdin=data)


def pointer_from_clean(
    result: RunResult, *, digest: str, size: int
) -> bytes:
    """Take a canonical pointer document out of a successful clean run."""
    document = extract_generated_pointer_document(
        result, digest=digest, size=size
    )
    require_generated_pointer_shape(document, digest=digest, size=size)
    return document


def pointer_from_clean_stdout(
    result: RunResult, *, digest: str, size: int
) -> bytes:
    """Take a canonical pointer document from clean's standard output only.

    A matching key/value block on stderr is not the document. Clean
    failure is never mapped to an empty pointer.
    """
    assert result.returncode == 0, (
        "clean failed "
        f"(exit {result.returncode}) argv={list(result.argv)!r}: "
        f"{result.stderr_text}"
    )
    stdout_ok = pointer_matches_digest_and_size(
        result.stdout, digest=digest, size=size
    )
    if not stdout_ok:
        raise AssertionError(
            "clean did not write a canonical pointer document on "
            "standard output; a matching block on stderr is not the "
            f"document: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    require_generated_pointer_shape(result.stdout, digest=digest, size=size)
    return result.stdout


def assert_object_bytes(store_root: Path, oid: str, content: bytes) -> Path:
    """Require the sharded object file exists and equals *content*.

    Same contract as ``require_object_bytes``. The name is the verdict
    the suite-bailout audit can see: a missing or mismatched object is
    not a stored object.
    """
    return require_object_bytes(store_root, oid, content)


def assert_object_absent(store_root: Path, oid: str) -> None:
    """Require the sharded object path does not exist.

    Same contract as ``require_object_absent``. The name is the verdict
    the suite-bailout audit can see: an unreadable parent is a hard
    failure, not absence.
    """
    require_object_absent(store_root, oid)


def assert_clean_wrote_canonical_pointer(
    result: RunResult, *, digest: str, size: int
) -> bytes:
    """Take a canonical pointer from clean stdout.

    Same contract as ``pointer_from_clean_stdout``. The name is the
    verdict the suite-bailout audit can see: clean that copies stdin
    through, or that writes the pointer only on stderr, is not a
    canonical-pointer write.
    """
    return pointer_from_clean_stdout(result, digest=digest, size=size)


def assert_generated_pointer_shape(
    document: bytes, *, digest: str, size: int
) -> list[tuple[str, str]]:
    """Require generated pointer shape without pinning the oid key.

    Same contract as ``require_generated_pointer_shape``. The name is
    the verdict the suite-bailout audit can see.
    """
    return require_generated_pointer_shape(document, digest=digest, size=size)


def smudge_skip_bytes(ws: Workspace, document: bytes) -> RunResult:
    """Run ``smudge --skip`` on *document*. Does not rewrite ``smudge_bytes``."""
    return ws.invoke_via_git(["smudge", "--skip"], stdin=document)


def install_local_keeping_process(ws: Workspace) -> dict[str, str]:
    """``install --local`` while keeping the process filter configured."""
    result = ws.invoke_via_git(["install", "--local"])
    require_success(result)
    return require_filters_point_at_git_orbulk(ws, local=True)


def track_pattern(ws: Workspace, glob: str) -> RunResult:
    """Setup: track *glob* via the track porcelain. Success is required."""
    result = run_track(ws, [glob])
    require_success(result)
    return result


def commit_tracked_payload(
    ws: Workspace, relpath: str, data: bytes
) -> str:
    """Write, add, and commit a tracked payload. Return independent SHA-256.

    Filters and track pattern must already be configured. A failed add or
    commit is not treated as a stored object.
    """
    ws.write(relpath, data)
    digest = sha256_hex(data)
    to_add = [relpath]
    try:
        ws.read_bytes(".gitattributes")
        to_add.append(".gitattributes")
    except FileNotFoundError:
        pass
    added = ws.git(["add", "--", *to_add])
    assert added.returncode == 0, (
        f"git add {to_add!r} failed (exit {added.returncode}): "
        f"{added.stderr_text}"
    )
    committed = ws.git(["commit", "-m", f"add {relpath}"])
    assert committed.returncode == 0, (
        f"git commit {relpath!r} failed (exit {committed.returncode}): "
        f"{committed.stderr_text}"
    )
    return digest


@contextmanager
def recording_http_server() -> Iterator[tuple[str, list[tuple[str, bytes]]]]:
    """Loopback HTTP server that records method and body. Not an LFS fake."""
    records: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def _record(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length else b""
            records.append((self.command, body))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            self._record()

        def do_PUT(self) -> None:
            self._record()

        def do_POST(self) -> None:
            self._record()

        def do_HEAD(self) -> None:
            records.append((self.command, b""))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield svc.url, records


def configure_storage_root(ws: Workspace, path: Path) -> None:
    """Setup: set the local object-store root (parent of the objects directory)."""
    require_git_config_set(ws, "lfs.storage", str(path), local=True)


def configure_fetch_include(ws: Workspace, pattern: str) -> None:
    """Setup: set include path pattern. Does not assert the key in output."""
    require_git_config_set(ws, "lfs.fetchinclude", pattern, local=True)


def configure_fetch_exclude(ws: Workspace, pattern: str) -> None:
    """Setup: set exclude path pattern. Does not assert the key in output."""
    require_git_config_set(ws, "lfs.fetchexclude", pattern, local=True)


def enable_skip_download_errors(ws: Workspace) -> None:
    """Setup: allow checkout to succeed when a smudge download fails."""
    require_git_config_set(
        ws, "lfs.skipdownloaderrors", "true", local=True
    )


def skip_download_errors_environment() -> dict[str, str]:
    """Environment mapping that enables skip-download-errors."""
    return {"GIT_ORBULK_SKIP_DOWNLOAD_ERRORS": "1"}


def enable_skip_smudge_environment() -> dict[str, str]:
    """Environment mapping that passes pointers through without downloading."""
    return {"GIT_ORBULK_SKIP_SMUDGE": "1"}


def configure_unreachable_endpoint(ws: Workspace) -> str:
    """Setup: point LFS at a loopback URL whose port is not listening."""
    port = reserve_loopback_port()
    url = f"http://127.0.0.1:{port}/{token()}/info/lfs"
    add_git_remote(ws, "origin", url)
    require_git_config_set(ws, "lfs.url", url, local=True)
    # Setup only: a closed loopback port refuses immediately, but extra
    # transfer retries would still multiply that refusal into a hang.
    require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
    require_git_config_set(ws, "lfs.transfer.maxretrydelay", "0", local=True)
    require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)
    return url


# ---------------------------------------------------------------------------
# F06: endpoint discovery and authentication (new names only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedApiRequest:
    """One recorded HTTP request. Not an LFS protocol fake."""

    method: str
    path: str
    host: str
    authorization: str
    status: int


def derived_https_endpoint(git_remote_url: str) -> str:
    """Append the conventional ``.git/info/lfs`` suffix (PRD FP-06).

    If *git_remote_url* already ends in ``.git``, append ``/info/lfs`` only.
    Does not implement URL aliases, ``file://``, or SSH host/path translation.
    """
    assert git_remote_url, "git remote URL is empty; cannot derive an endpoint"
    url = git_remote_url.rstrip("/")
    if url.endswith(".git"):
        return url + "/info/lfs"
    return url + ".git/info/lfs"


def _basic_userpass(header: str) -> tuple[str, str] | None:
    """Decode an Authorization value as HTTP Basic user/password.

    Returns None when the header is empty or is not valid Basic. A
    present but non-Basic / undecodable value is not mapped to absence
    by callers — they treat it as "carried other material".
    """
    if not header or not header.strip():
        return None
    parts = header.split(None, 1)
    if len(parts) != 2:
        return None
    kind, blob = parts
    if kind.casefold() != "basic":
        return None
    try:
        raw = base64.b64decode(blob, validate=True)
        text = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in text:
        return None
    user, password = text.split(":", 1)
    return user, password


def _host_from_url_or_host(url_or_host: str) -> str:
    """Return the host[:port] used to classify contact. Empty is unclassified."""
    assert url_or_host, (
        "url_or_host is empty; cannot classify whether a server was contacted"
    )
    parsed = urlparse(url_or_host)
    if parsed.netloc:
        return parsed.netloc
    host = url_or_host.split("/", 1)[0]
    assert host, (
        f"cannot classify contact host from {url_or_host!r}"
    )
    return host


def _auth_gate_status(
    authorization: str, accepted_user: str, accepted_password: str
) -> int:
    pair = _basic_userpass(authorization)
    if pair is None:
        return 401
    user, password = pair
    if user == accepted_user and password == accepted_password:
        return 200
    return 401


@contextmanager
def recording_api_server(
    *,
    accepted_user: str | None = None,
    accepted_password: str | None = None,
) -> Iterator[tuple[str, list[RecordedApiRequest]]]:
    """Loopback HTTP server that records method, path, Host, Authorization.

    Open mode (both credentials omitted): every request is 200.
    Credential-gate mode (both credentials required): missing or
    non-matching Basic is 401 with a Basic challenge; matching Basic is
    200. A present Authorization that is not valid Basic is 401, never
    mapped to "absent". Not an LFS protocol fake.
    """
    if (accepted_user is None) != (accepted_password is None):
        raise AssertionError(
            "recording_api_server credential gate requires both "
            "accepted_user and accepted_password, or neither"
        )
    gated = accepted_user is not None
    records: list[RecordedApiRequest] = []

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            authorization = self.headers.get("Authorization") or ""
            host = self.headers.get("Host") or ""
            if gated:
                status = _auth_gate_status(
                    authorization, accepted_user, accepted_password
                )
            else:
                status = 200
            records.append(
                RecordedApiRequest(
                    method=self.command,
                    path=self.path,
                    host=host,
                    authorization=authorization,
                    status=status,
                )
            )
            self.send_response(status)
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="lfs"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield svc.url, records


def contacts(
    records: list[RecordedApiRequest] | None, *, url_or_host: str
) -> bool:
    """True when *records* include a request whose Host matches *url_or_host*.

    An empty list is classified absence (False). A missing records object
    or an unclassifiable *url_or_host* is a hard failure, not absence.
    """
    assert records is not None, (
        "API request log is missing; cannot classify contact"
    )
    needle = _host_from_url_or_host(url_or_host)
    for rec in records:
        host = rec.host
        assert host is not None, (
            f"recorded request has no Host field: {rec!r}"
        )
        if host == needle or host.rstrip("/") == needle:
            return True
        rec_parsed = urlparse(f"http://{host}")
        if rec_parsed.netloc == needle:
            return True
    return False


def require_request_carries_basic(
    records: list[RecordedApiRequest] | None, username: str, password: str
) -> RecordedApiRequest:
    """Require some recorded request carries HTTP Basic for *username*/*password*.

    Empty records or no Authorization at all is a hard failure (not
    "didn't carry"). A present Authorization that is not this pair is
    "carried other material", never mapped to absence.
    """
    assert records is not None, (
        "API request log is missing; cannot observe Basic material"
    )
    assert records, (
        "no API requests recorded; cannot observe HTTP Basic material"
    )
    assert username != "" or password != "", (
        "expected Basic pair is empty; cannot classify matching material"
    )
    other_present = False
    for rec in records:
        if not rec.authorization:
            continue
        pair = _basic_userpass(rec.authorization)
        if pair is None:
            other_present = True
            continue
        if pair == (username, password):
            return rec
        other_present = True
    if other_present:
        raise AssertionError(
            "recorded Authorization material was not the expected Basic pair "
            f"(user={username!r})"
        )
    raise AssertionError(
        "no recorded request carried HTTP Basic material "
        f"(user={username!r})"
    )


def records_include_basic(
    records: list[RecordedApiRequest] | None, username: str, password: str
) -> bool:
    """True when some recorded request carries this Basic pair.

    Missing records object is unclassified. Empty records, or records
    whose Authorization is absent or a different pair, are False — that
    is classified absence of *this* pair, not a probe failure.
    """
    assert records is not None, (
        "API request log is missing; cannot classify Basic material"
    )
    for rec in records:
        if not rec.authorization:
            continue
        pair = _basic_userpass(rec.authorization)
        if pair == (username, password):
            return True
    return False


def fake_ssh_authenticate(
    script_dir: str | Path,
    *,
    stdout_json: str,
    stderr_text: str = "",
    exit_code: int = 0,
) -> tuple[dict[str, str | None], Path]:
    """Write an executable fake SSH that logs argv and answers authenticate.

    Returns ``(env_updates, argv_log_path)``. *env_updates* sets
    ``GIT_SSH`` to the script and unsets ``GIT_SSH_COMMAND`` so the
    product invokes the script without a shell. Invocations that do not
    name git-orbulk-authenticate exit 1 so Git itself cannot hang. A log
    write failure is a hard failure when the log is later read.
    """
    directory = Path(script_dir)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"sshlog_{token()}"
    script_path = directory / f"fakessh_{token()}"
    script_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        f"log_path = {str(log_path)!r}\n"
        "argv = sys.argv[1:]\n"
        "with open(log_path, 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps(argv) + '\\n')\n"
        "joined = ' '.join(argv)\n"
        "if 'git-orbulk-authenticate' not in joined:\n"
        "    sys.exit(1)\n"
        f"sys.stderr.write({stderr_text!r})\n"
        f"sys.stdout.write({stdout_json!r})\n"
        f"sys.exit({int(exit_code)})\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    env_updates: dict[str, str | None] = {
        "GIT_SSH": str(script_path),
        "GIT_SSH_COMMAND": None,
    }
    return env_updates, log_path


def require_authenticate_invocation(
    argv_log: str | Path,
    *,
    repo_path_fragment: str,
    operation: str,
) -> str:
    """Require the fake-SSH argv log contains git-orbulk-authenticate.

    The log must name git-orbulk-authenticate, *repo_path_fragment*, and
    *operation* (``download`` or ``upload``). A missing or unreadable log
    is a hard failure, not "helper was not invoked".
    """
    assert operation in ("download", "upload"), (
        f"authenticate operation must be download or upload, got {operation!r}"
    )
    assert repo_path_fragment, "repo path fragment is empty"
    path = Path(argv_log)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AssertionError(
            f"authenticate argv log is missing at {path}; "
            "git-orbulk-authenticate was not invoked"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot read authenticate argv log {path}: {exc}"
        ) from exc
    assert text.strip(), (
        "authenticate argv log is empty; git-orbulk-authenticate was not invoked"
    )
    matched = False
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            argv = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"authenticate argv log line is not JSON: {line!r} ({exc})"
            ) from exc
        blob = " ".join(str(item) for item in argv)
        if "git-orbulk-authenticate" not in blob:
            continue
        if repo_path_fragment not in blob:
            continue
        if operation not in blob:
            continue
        matched = True
        break
    assert matched, (
        "no git-orbulk-authenticate invocation named the repository path "
        f"fragment {repo_path_fragment!r} and operation {operation!r}: "
        f"{text!r}"
    )
    return text


def force_hybrid_ssh(ws: Workspace) -> None:
    """Setup: keep SSH remotes on the hybrid HTTPS API path (not FP-17)."""
    require_git_config_set(ws, "lfs.sshtransfer", "never", local=True)


def install_credential_helper(
    ws: Workspace, username: str, password: str
) -> Path:
    """Setup: install a Git credential helper that emits *username*/*password*."""
    assert username, "credential helper username is empty"
    path = ws.home / f"cred_{token()}"
    path.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = get ]; then\n'
        f"  printf '%s\\n' 'username={username}'\n"
        f"  printf '%s\\n' 'password={password}'\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    require_git_config_set(ws, "credential.helper", str(path), local=True)
    return path


def prepare_tracked_commit(ws: Workspace, relpath: str, data: bytes) -> str:
    """Setup: install filters, track by suffix, commit *data* at *relpath*."""
    install_local_keeping_process(ws)
    suffix = Path(relpath).suffix
    assert suffix, (
        f"tracked relpath {relpath!r} has no suffix for a track glob"
    )
    track_pattern(ws, f"*{suffix}")
    digest = commit_tracked_payload(ws, relpath, data)
    require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
    require_git_config_set(ws, "lfs.transfer.maxretrydelay", "0", local=True)
    require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)
    return digest


# ---------------------------------------------------------------------------
# F07: batch negotiation and basic object transfer (new names only)
# ---------------------------------------------------------------------------

TRANSFERS_LIST_OMITTED = object()

_OVERLAP_WAIT_SECONDS = 4.0
_EXPIRED_AT_PAST = "1999-01-01T00:00:00Z"


@dataclass(frozen=True)
class RecordedHttpExchange:
    """One recorded HTTP request to a conforming batch/basic fixture."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class ParsedBatchRequest:
    """Parsed objects-batch POST. ``transfers`` may be the omitted sentinel."""

    operation: str
    objects: tuple[tuple[str, int], ...]
    transfers: object
    path: str
    headers: dict[str, str]


class ConformingBatchServer:
    """Loopback Git Orbulk batch + basic transfer fixture state."""

    def __init__(
        self,
        *,
        url: str,
        records: list[RecordedHttpExchange],
        header_name: str,
        header_value: str,
        action_paths: dict[str, str],
        verify_paths: dict[str, str],
        payloads: dict[str, bytes],
        state: dict[str, int],
    ) -> None:
        self.url = url
        self.records = records
        self.header_name = header_name
        self.header_value = header_value
        self.action_paths = action_paths
        self.verify_paths = verify_paths
        self.payloads = payloads
        self._state = state

    @property
    def max_in_flight(self) -> int:
        return int(self._state["max_in_flight"])

    def action_path(self, oid: str | None = None) -> str:
        if oid is None:
            assert len(self.action_paths) == 1, (
                "action_path() without oid requires exactly one registered "
                f"object, got {list(self.action_paths)!r}"
            )
            return next(iter(self.action_paths.values()))
        assert oid in self.action_paths, (
            f"no action path for oid {oid!r}; known={list(self.action_paths)!r}"
        )
        return self.action_paths[oid]

    def verify_path(self, oid: str | None = None) -> str:
        if oid is None:
            assert len(self.verify_paths) == 1, (
                "verify_path() without oid requires exactly one registered "
                f"object, got {list(self.verify_paths)!r}"
            )
            return next(iter(self.verify_paths.values()))
        assert oid in self.verify_paths, (
            f"no verify path for oid {oid!r}; known={list(self.verify_paths)!r}"
        )
        return self.verify_paths[oid]

    def action_href(self, oid: str | None = None) -> str:
        return self.url.rstrip("/") + self.action_path(oid)

    def verify_href(self, oid: str | None = None) -> str:
        return self.url.rstrip("/") + self.verify_path(oid)


def contract_git_orbulk_json_media_type() -> str:
    """Designated Git Orbulk JSON media type (Interface Contract)."""
    return "application/vnd.git-orbulk+json"


def contract_objects_batch_path() -> str:
    """Endpoint objects-batch path (Interface Contract)."""
    return "/objects/batch"


def contract_basic_adapter_name() -> str:
    """Basic transfer adapter name advertised on the batch request (FP-07)."""
    return "basic"


def contract_tus_adapter_name() -> str:
    """Tus path adapter name as it appears in the advertised transfer list."""
    return "tus"


def _header_ci(headers: Mapping[str, str], name: str) -> str | None:
    want = name.casefold()
    found: list[str] = []
    for key, value in headers.items():
        if str(key).casefold() == want:
            found.append(str(value))
    if not found:
        return None
    assert len(found) == 1, (
        f"header {name!r} appeared more than once: {found!r}"
    )
    return found[0]


def _request_path(path: str) -> str:
    parsed = urlparse(path)
    if parsed.scheme and parsed.netloc:
        return parsed.path or "/"
    return path.split("?", 1)[0]


def _is_objects_batch_path(path: str) -> bool:
    cleaned = _request_path(path).rstrip("/")
    batch = contract_objects_batch_path().rstrip("/")
    return cleaned == batch or cleaned.endswith(batch)


def _media_type_named(header_value: str, designated: str) -> bool:
    """True when *header_value* names *designated* as a type/subtype.

    Ignores optional parameters (including charset) and case. An Accept
    list may name several types; naming the designated type is enough.
    """
    want = designated.casefold().strip()
    assert want, "designated media type is empty"
    for part in header_value.split(","):
        type_sub = part.split(";", 1)[0].strip().casefold()
        if type_sub == want:
            return True
    return False


def _read_handler_body(handler: BaseHTTPRequestHandler) -> bytes:
    encoding = handler.headers.get("Transfer-Encoding") or ""
    if "chunked" in encoding.casefold():
        chunks: list[bytes] = []
        while True:
            line = handler.rfile.readline()
            if not line:
                break
            size_s = line.split(b";", 1)[0].strip()
            try:
                size = int(size_s, 16)
            except ValueError:
                return b""
            if size == 0:
                while True:
                    extra = handler.rfile.readline()
                    if extra in (b"\r\n", b"\n", b""):
                        break
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.read(2)
        return b"".join(chunks)
    length_s = handler.headers.get("Content-Length")
    if not length_s:
        return b""
    try:
        length = int(length_s)
    except ValueError:
        return b""
    if length < 0:
        return b""
    return handler.rfile.read(length)


def _parse_mode_set(mode: str) -> frozenset[str]:
    parts = {
        item.strip()
        for item in mode.replace("+", ",").split(",")
        if item.strip()
    }
    assert parts, f"conforming_batch_server mode is empty: {mode!r}"
    return frozenset(parts)


def _parse_transfers_field(body: object) -> object:
    if not isinstance(body, dict):
        raise AssertionError(
            f"batch JSON is not an object: {body!r}"
        )
    if "transfers" not in body:
        return TRANSFERS_LIST_OMITTED
    raw = body["transfers"]
    if not isinstance(raw, list):
        raise AssertionError(
            f"batch transfers field is not a list: {raw!r}"
        )
    names: list[str] = []
    for item in raw:
        names.append(str(item))
    return names


def _advertises_non_basic(transfers: object) -> bool:
    if transfers is TRANSFERS_LIST_OMITTED:
        return False
    if not isinstance(transfers, list):
        raise AssertionError(
            f"transfers is not a list or omitted: {transfers!r}"
        )
    basic = contract_basic_adapter_name()
    return any(name != basic for name in transfers)


def _send_bytes(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: bytes,
    *,
    content_type: str | None = None,
) -> None:
    handler.send_response(status)
    if content_type is not None:
        handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


@contextmanager
def conforming_batch_server(
    *,
    mode: str,
    payloads: Sequence[bytes] | None = None,
    header_name: str | None = None,
    header_value: str | None = None,
) -> Iterator[ConformingBatchServer]:
    """Loopback Git Orbulk batch + basic transfer server.

    POST to the objects-batch path is negotiation only when Accept and
    Content-Type both name the designated JSON media type. GET/PUT on
    action hrefs require the advertised header and carry raw object
    bytes. A verify href accepts any HTTP method. Not F06's non-LFS
    recorders.
    """
    modes = _parse_mode_set(mode)
    payload_list = list(payloads or ())
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    verify_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    verify_path_set: set[str] = set()
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        verify = f"/vf_{token()}"
        action_paths[oid] = action
        verify_paths[oid] = verify
        path_to_oid[action] = oid
        verify_path_set.add(verify)
    hdr_name = header_name if header_name is not None else f"X-T{token()}"
    hdr_value = header_value if header_value is not None else f"v{token()}"
    records: list[RecordedHttpExchange] = []
    state = {"max_in_flight": 0, "in_flight": 0}
    gate = threading.Condition()
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()
    overlap = "overlap_gate" in modes

    def _headers_dict(handler: BaseHTTPRequestHandler) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in handler.headers.items():
            out[str(key)] = str(value)
        return out

    def _gate_transfer() -> None:
        with gate:
            state["in_flight"] += 1
            if state["in_flight"] > state["max_in_flight"]:
                state["max_in_flight"] = state["in_flight"]
            gate.notify_all()
            if overlap and state["in_flight"] < 2:
                gate.wait(timeout=_OVERLAP_WAIT_SECONDS)

    def _ungate_transfer() -> None:
        with gate:
            state["in_flight"] = max(0, state["in_flight"] - 1)
            gate.notify_all()

    def _header_ok(handler: BaseHTTPRequestHandler) -> bool:
        observed = handler.headers.get(hdr_name)
        return observed == hdr_value

    def _batch_object(
        oid: str,
        size: int,
        operation: str,
        transfers: object,
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "oid": oid,
            "size": size,
            "authenticated": True,
        }
        if "object_error" in modes:
            item["error"] = {"code": 404, "message": "unavailable"}
            return item
        if "already_exists" in modes:
            return item
        if "basic_only_peer" in modes and _advertises_non_basic(transfers):
            return item
        href_oid = oid if oid in action_paths else None
        if href_oid is None and action_paths:
            href_oid = next(iter(action_paths))
        if href_oid is None:
            return item
        href = "http://placeholder" + action_paths[href_oid]
        action: dict[str, object] = {
            "href": href,
            "header": {hdr_name: hdr_value},
        }
        if "expired" in modes:
            action["expires_at"] = _EXPIRED_AT_PAST
        actions: dict[str, object] = {}
        if operation == "download":
            actions["download"] = action
        else:
            actions["upload"] = action
            if "with_verify" in modes:
                actions["verify"] = {
                    "href": "http://placeholder" + verify_paths[href_oid],
                    "header": {hdr_name: hdr_value},
                }
        item["actions"] = actions
        return item

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = _headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in verify_path_set:
                _send_bytes(self, 200, b"")
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            if path in path_to_oid and self.command == "PUT":
                self._serve_put(path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            try:
                transfers = _parse_transfers_field(parsed)
            except AssertionError:
                _send_bytes(self, 400, b"")
                return
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                reply_objects.append(
                    _batch_object(oid, size, operation, transfers)
                )
            origin = f"http://{self.headers.get('Host') or '127.0.0.1'}"
            for item in reply_objects:
                actions = item.get("actions")
                if not isinstance(actions, dict):
                    continue
                for _name, action in actions.items():
                    if not isinstance(action, dict):
                        continue
                    href = str(action.get("href") or "")
                    if href.startswith("http://placeholder"):
                        action["href"] = origin + href[len("http://placeholder"):]
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if not _header_ok(self):
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            data = by_oid[oid]
            # Send headers before the overlap latch so the first worker can
            # signal auth-ok and a second GET can start while the body waits.
            if overlap and self.command == "GET":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.flush()
                _gate_transfer()
                try:
                    self.wfile.write(data)
                    self.wfile.flush()
                finally:
                    _ungate_transfer()
                return
            _gate_transfer()
            try:
                _send_bytes(
                    self,
                    200,
                    data,
                    content_type="application/octet-stream",
                )
            finally:
                _ungate_transfer()

        def _serve_put(self, path: str, body: bytes) -> None:
            if not _header_ok(self):
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            expected = by_oid[oid]
            _gate_transfer()
            try:
                if body != expected:
                    _send_bytes(self, 400, b"")
                    return
                _send_bytes(self, 200, b"")
            finally:
                _ungate_transfer()

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def do_PATCH(self) -> None:
            self._handle()

        def do_DELETE(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield ConformingBatchServer(
            url=svc.url,
            records=records,
            header_name=hdr_name,
            header_value=hdr_value,
            action_paths=action_paths,
            verify_paths=verify_paths,
            payloads=by_oid,
            state=state,
        )


def require_named_media_type(headers: Mapping[str, str]) -> tuple[str, str]:
    """Require Accept and Content-Type both name the designated media type."""
    accept = _header_ci(headers, "Accept")
    content_type = _header_ci(headers, "Content-Type")
    assert accept is not None, (
        f"batch request has no Accept header: {dict(headers)!r}"
    )
    assert content_type is not None, (
        f"batch request has no Content-Type header: {dict(headers)!r}"
    )
    designated = contract_git_orbulk_json_media_type()
    assert _media_type_named(accept, designated), (
        "Accept does not name the designated Git Orbulk JSON media type: "
        f"{accept!r}"
    )
    assert _media_type_named(content_type, designated), (
        "Content-Type does not name the designated Git Orbulk JSON media type: "
        f"{content_type!r}"
    )
    return accept, content_type


def require_batch_post(
    records: list[RecordedHttpExchange] | None,
    *,
    operation: str,
) -> ParsedBatchRequest:
    """Require a POST to the objects-batch path naming *operation*.

    JSON that cannot be parsed is a hard failure, never an omitted
    transfers list. A missing ``transfers`` key is the omitted sentinel,
    distinct from an empty list.
    """
    assert records is not None, (
        "HTTP request log is missing; cannot classify a batch POST"
    )
    assert operation in ("download", "upload"), (
        f"batch operation must be download or upload, got {operation!r}"
    )
    found: list[RecordedHttpExchange] = []
    for rec in records:
        if rec.method == "POST" and _is_objects_batch_path(rec.path):
            found.append(rec)
    assert found, (
        "no POST to the objects-batch path; "
        f"records={[(r.method, r.path) for r in records]!r}"
    )
    rec = found[0]
    require_named_media_type(rec.headers)
    try:
        text = rec.body.decode("utf-8")
        body = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError(
            f"batch POST body is not JSON: {rec.body!r} ({exc})"
        ) from exc
    if not isinstance(body, dict):
        raise AssertionError(f"batch POST JSON is not an object: {body!r}")
    observed = str(body.get("operation") or "")
    assert observed == operation, (
        f"batch POST operation is {observed!r}, expected {operation!r}"
    )
    raw_objects = body.get("objects")
    assert isinstance(raw_objects, list), (
        f"batch POST has no objects list: {body!r}"
    )
    objects: list[tuple[str, int]] = []
    for item in raw_objects:
        assert isinstance(item, dict), f"batch object is not an object: {item!r}"
        oid = str(item.get("oid") or "")
        assert oid, f"batch object has no oid: {item!r}"
        try:
            size = int(item.get("size"))
        except (TypeError, ValueError) as exc:
            raise AssertionError(
                f"batch object size is not an integer: {item!r}"
            ) from exc
        objects.append((oid, size))
    transfers = _parse_transfers_field(body)
    return ParsedBatchRequest(
        operation=observed,
        objects=tuple(objects),
        transfers=transfers,
        path=rec.path,
        headers=dict(rec.headers),
    )


def advertised_adapter_names(parsed: ParsedBatchRequest) -> object:
    """Return the advertised transfer list, or the omitted sentinel."""
    return parsed.transfers


def require_advanced_advertised(parsed: ParsedBatchRequest) -> list[str]:
    """Require the list includes the tus adapter name and basic.

    Other names are allowed. An omitted list is not an advanced
    advertisement.
    """
    names = advertised_adapter_names(parsed)
    assert names is not TRANSFERS_LIST_OMITTED, (
        "advertised transfer list was omitted; advanced adapter was absent"
    )
    assert isinstance(names, list), (
        f"advertised transfer list is not a list: {names!r}"
    )
    tus = contract_tus_adapter_name()
    basic = contract_basic_adapter_name()
    assert tus in names, (
        f"advertised transfer list does not include {tus!r}: {names!r}"
    )
    assert basic in names, (
        f"advertised transfer list does not include {basic!r} in addition "
        f"to the advanced adapter: {names!r}"
    )
    return names


def require_basic_only_or_omitted(parsed: ParsedBatchRequest) -> object:
    """Require advanced names are absent: only basic, or the list omitted."""
    names = advertised_adapter_names(parsed)
    tus = contract_tus_adapter_name()
    basic = contract_basic_adapter_name()
    if names is TRANSFERS_LIST_OMITTED:
        return names
    assert isinstance(names, list), (
        f"advertised transfer list is not a list: {names!r}"
    )
    assert tus not in names, (
        f"advanced adapter {tus!r} still advertised: {names!r}"
    )
    assert names == [basic], (
        "advertised transfer list is not only basic (and not omitted): "
        f"{names!r}"
    )
    return names


def require_put_of(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> RecordedHttpExchange:
    """Require a PUT whose body is exactly *content*."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify a PUT"
    )
    matched = [rec for rec in records if rec.method == "PUT" and rec.body == content]
    assert matched, (
        "no PUT of the original object bytes; "
        f"puts={[ (r.path, len(r.body)) for r in records if r.method == 'PUT' ]!r}"
    )
    return matched[0]


def require_no_put_of(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> None:
    """Require that no PUT carried exactly *content*."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify absence of a PUT"
    )
    matched = [rec for rec in records if rec.method == "PUT" and rec.body == content]
    assert not matched, (
        "PUT of the original object bytes was not omitted: "
        f"{[(r.method, r.path) for r in matched]!r}"
    )


def require_get_of_href(
    records: list[RecordedHttpExchange] | None,
    path: str,
    *,
    header_name: str,
    header_value: str,
) -> RecordedHttpExchange:
    """Require a GET of *path* that forwards the supplied header pair."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify a GET"
    )
    want = _request_path(path)
    gets = [
        rec
        for rec in records
        if rec.method == "GET" and _request_path(rec.path) == want
    ]
    assert gets, (
        f"no GET of action href {want!r}; "
        f"records={[(r.method, r.path) for r in records]!r}"
    )
    rec = gets[0]
    observed = _header_ci(rec.headers, header_name)
    assert observed is not None, (
        f"GET of {want!r} did not carry header {header_name!r}: "
        f"{dict(rec.headers)!r}"
    )
    assert observed == header_value, (
        f"GET of {want!r} forwarded {header_name!r}={observed!r}, "
        f"not {header_value!r}"
    )
    return rec


def require_href_contacted_after_put(
    records: list[RecordedHttpExchange] | None,
    content: bytes,
    path: str,
) -> RecordedHttpExchange:
    """Require an HTTP request to *path* after a PUT of *content*.

    Any method counts as contact. Missing PUT, missing contact, or
    contact earlier than the PUT is a hard failure.
    """
    assert records is not None, (
        "HTTP request log is missing; cannot classify verify contact"
    )
    put = require_put_of(records, content)
    put_index = records.index(put)
    want = _request_path(path)
    later = [
        rec
        for rec in records[put_index + 1 :]
        if _request_path(rec.path) == want
    ]
    assert later, (
        f"no HTTP request to {want!r} after PUT of the object bytes; "
        f"records={[(r.method, r.path) for r in records]!r}"
    )
    return later[0]


def require_bound_prevents_overlap_unlike_unbounded(
    bound_max_in_flight: int, unbounded_max_in_flight: int
) -> tuple[int, int]:
    """Require bound-1 did not overlap, counted only when unbounded did.

    Default parallelism greater than one is the live baseline: an otherwise
    identical unbounded run of the same two missing objects must overlap
    (max_in_flight >= 2). The bound-1 arm of that same pair must then stay
    at max_in_flight == 1. A serial-always client that ignores the
    concurrent-transfers setting produces 1 on both arms and is not
    honoring the bound.
    """
    assert unbounded_max_in_flight >= 2, (
        "unbounded run of the same two missing objects never overlapped "
        f"(max_in_flight={unbounded_max_in_flight}); bound-to-1 is not "
        "distinguishable from always-serial"
    )
    assert bound_max_in_flight == 1, (
        "configured bound of 1 still overlapped in-flight transfers "
        f"(max_in_flight={bound_max_in_flight}) while the unbounded run "
        f"overlapped (max_in_flight={unbounded_max_in_flight})"
    )
    return bound_max_in_flight, unbounded_max_in_flight


def require_no_contact_of(
    records: list[RecordedHttpExchange] | None, path: str
) -> None:
    """Require that no recorded request targeted *path*."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify contact absence"
    )
    want = _request_path(path)
    hits = [rec for rec in records if _request_path(rec.path) == want]
    assert not hits, (
        f"unexpected contact of {want!r}: "
        f"{[(r.method, r.path) for r in hits]!r}"
    )


def assert_no_contact_of(
    records: list[RecordedHttpExchange] | None, path: str
) -> None:
    """Require that no recorded request targeted *path*.

    Same contract as ``require_no_contact_of``. The name is the verdict
    the suite-bailout audit can see: a GET of the action path is still
    a download.
    """
    require_no_contact_of(records, path)


def assert_batch_post(
    records: list[RecordedHttpExchange] | None,
    *,
    operation: str,
) -> ParsedBatchRequest:
    """Require a POST to the objects-batch path naming *operation*.

    Same contract as ``require_batch_post``. The name is the verdict
    the suite-bailout audit can see: a fetch or push that never posts
    a batch is not batch negotiation.
    """
    return require_batch_post(records, operation=operation)


def assert_get_of_href(
    records: list[RecordedHttpExchange] | None,
    path: str,
    *,
    header_name: str,
    header_value: str,
) -> RecordedHttpExchange:
    """Require a GET of *path* that forwards the supplied header pair.

    Same contract as ``require_get_of_href``. The name is the verdict
    the suite-bailout audit can see: a download that never GETs the
    action href with the supplied headers is not a basic download.
    """
    return require_get_of_href(
        records,
        path,
        header_name=header_name,
        header_value=header_value,
    )


def assert_put_of(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> RecordedHttpExchange:
    """Require a PUT whose body is exactly *content*.

    Same contract as ``require_put_of``. The name is the verdict the
    suite-bailout audit can see: an upload that never PUTs the object
    bytes is not a basic upload.
    """
    return require_put_of(records, content)


def assert_no_put_of(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> None:
    """Require that no PUT carried exactly *content*.

    Same contract as ``require_no_put_of``. The name is the verdict
    the suite-bailout audit can see: a client that still PUTs after
    already-exists has not omitted the second upload.
    """
    require_no_put_of(records, content)


def assert_advanced_advertised(parsed: ParsedBatchRequest) -> list[str]:
    """Require the list includes the tus adapter name and basic.

    Same contract as ``require_advanced_advertised``. The name is the
    verdict the suite-bailout audit can see: a client that omits the
    advanced adapter, or omits the list, has not advertised tus in
    addition to basic.
    """
    return require_advanced_advertised(parsed)


def assert_basic_only_or_omitted(parsed: ParsedBatchRequest) -> object:
    """Require advanced names are absent: only basic, or the list omitted.

    Same contract as ``require_basic_only_or_omitted``. The name is the
    verdict the suite-bailout audit can see: a client that still
    advertises the advanced adapter is not on the basic-only arm.
    """
    return require_basic_only_or_omitted(parsed)


def enable_tus_transfers(ws: Workspace) -> None:
    """Setup: explicitly enable the tus transfer path. Does not assert output."""
    require_git_config_set(ws, "lfs.tustransfers", "true", local=True)


def enable_basic_transfers_only(ws: Workspace) -> None:
    """Setup: enable basic-transfers-only. Does not assert output."""
    require_git_config_set(ws, "lfs.basictransfersonly", "true", local=True)


def configure_concurrent_transfers(ws: Workspace, n: int) -> None:
    """Setup: set the concurrent-transfer bound. Does not assert output."""
    require_git_config_set(
        ws, "lfs.concurrenttransfers", str(n), local=True
    )


def remove_stored_object(ws: Workspace, oid: str) -> None:
    """Delete a sharded object that must already exist.

    Missing or unreadable is a hard failure, never 'already absent'.
    """
    path = default_lfs_store_root(ws) / sharded_object_rel(oid)
    try:
        path.unlink()
    except FileNotFoundError:
        raise AssertionError(
            f"cannot remove stored object; missing at {path}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot remove stored object at {path}: {exc}"
        ) from exc


def point_lfs_at(ws: Workspace, endpoint_url: str) -> None:
    """Setup: add origin and set lfs.url to *endpoint_url*."""
    add_git_remote(ws, "origin", endpoint_url)
    require_git_config_set(ws, "lfs.url", endpoint_url, local=True)
    require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
    require_git_config_set(ws, "lfs.transfer.maxretrydelay", "0", local=True)
    require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)


# ---------------------------------------------------------------------------
# F08: fetch / pull / checkout / clone observation
# ---------------------------------------------------------------------------


def _workspace_rel(ws: Workspace, relpath: str, cwd: str | Path | None) -> str:
    """Return *relpath* as a workspace-relative path, optionally under *cwd*."""
    if cwd is None:
        return relpath
    root = Path(cwd).resolve()
    base = ws.path.resolve()
    try:
        nested = root.relative_to(base)
    except ValueError as exc:
        raise AssertionError(
            f"cwd {root} is not inside workspace {base}"
        ) from exc
    return str(nested / relpath)


def git_dir_at(ws: Workspace, cwd: str | Path) -> Path:
    """Return the Git directory of the repository at *cwd*.

    A failed ``rev-parse`` is not treated as absence of a Git directory.
    """
    result = ws.git(["rev-parse", "--git-dir"], cwd=cwd)
    assert result.returncode == 0, (
        "git rev-parse --git-dir failed "
        f"(exit {result.returncode}) cwd={cwd}: {result.stderr_text}"
    )
    raw = result.stdout_text.strip()
    assert raw, "git rev-parse --git-dir produced no path"
    path = Path(raw)
    if not path.is_absolute():
        path = (Path(cwd) / path).resolve()
    else:
        path = path.resolve()
    return path


def default_lfs_store_root_at(ws: Workspace, cwd: str | Path) -> Path:
    """Default local object-store root of the repository at *cwd*."""
    return git_dir_at(ws, cwd) / "lfs"


def require_git_repository_at(ws: Workspace, cwd: str | Path) -> Path:
    """Require *cwd* is a usable Git repository. Failure is not absence."""
    return git_dir_at(ws, cwd)


def require_working_tree_bytes(
    ws: Workspace,
    relpath: str,
    content: bytes,
    *,
    cwd: str | Path | None = None,
) -> bytes:
    """Require the working-tree file equals *content*.

    Missing or not a regular file is a hard failure, never empty bytes.
    """
    rel = _workspace_rel(ws, relpath, cwd)
    try:
        data = ws.read_bytes(rel)
    except FileNotFoundError:
        raise AssertionError(
            f"working-tree file {relpath!r} is missing"
        ) from None
    assert data == content, (
        f"working-tree file {relpath!r} is not the expected bytes "
        f"(got {len(data)} bytes, expected {len(content)})"
    )
    return data


def require_working_tree_pointer(
    ws: Workspace,
    relpath: str,
    *,
    digest: str,
    size: int,
    cwd: str | Path | None = None,
) -> bytes:
    """Require the working-tree file is a pointer for *digest*/*size*.

    Missing is a hard failure. A document that cannot be classified as
    that pointer is a hard failure, never 'not a pointer'.
    """
    rel = _workspace_rel(ws, relpath, cwd)
    try:
        data = ws.read_bytes(rel)
    except FileNotFoundError:
        raise AssertionError(
            f"working-tree file {relpath!r} is missing"
        ) from None
    assert pointer_matches_digest_and_size(
        data, digest=digest, size=size
    ), (
        "working-tree file is not a pointer document for digest "
        f"{digest!r} size={size}: {relpath!r} bytes={data!r}"
    )
    return data


def assert_working_tree_bytes(
    ws: Workspace,
    relpath: str,
    content: bytes,
    *,
    cwd: str | Path | None = None,
) -> bytes:
    """Require the working-tree file equals *content*.

    Same contract as ``require_working_tree_bytes``. The name is the
    verdict the suite-bailout audit can see: a missing or mismatched
    working-tree file is not materialization.
    """
    return require_working_tree_bytes(ws, relpath, content, cwd=cwd)


def assert_working_tree_pointer(
    ws: Workspace,
    relpath: str,
    *,
    digest: str,
    size: int,
    cwd: str | Path | None = None,
) -> bytes:
    """Require the working-tree file is a pointer for *digest*/*size*.

    Same contract as ``require_working_tree_pointer``. The name is the
    verdict the suite-bailout audit can see: a document that is not
    that pointer is not a leftover placeholder.
    """
    return require_working_tree_pointer(
        ws, relpath, digest=digest, size=size, cwd=cwd
    )


def write_pointer_placeholders_from_index(
    ws: Workspace, relpaths: Sequence[str]
) -> dict[str, bytes]:
    """Setup: replace working-tree files with the index pointer blobs."""
    written: dict[str, bytes] = {}
    for relpath in relpaths:
        blob = index_blob(ws, relpath)
        ws.write(relpath, blob)
        written[relpath] = blob
    return written


def snapshot_working_tree(
    ws: Workspace,
    relpaths: Sequence[str],
    *,
    cwd: str | Path | None = None,
) -> dict[str, bytes]:
    """Read working-tree files. A failed read is not an empty snapshot."""
    out: dict[str, bytes] = {}
    for relpath in relpaths:
        rel = _workspace_rel(ws, relpath, cwd)
        try:
            out[relpath] = ws.read_bytes(rel)
        except FileNotFoundError:
            raise AssertionError(
                f"working-tree snapshot: {relpath!r} is missing"
            ) from None
    return out


def require_download_batch_accounts_for_oids(
    records: list[RecordedHttpExchange] | None,
    oids: Sequence[str],
) -> list[set[str]]:
    """Require download batch POSTs account for *oids* as a full set.

    Every objects-batch POST body must parse as JSON (failure is not an
    omitted list). Download POSTs whose listed oids intersect *oids*
    must list the whole measured set — a proper-subset intersecting
    POST is a failure. At least one download POST must list the
    full set. Does not require media types or GET-href identity.
    """
    assert records is not None, (
        "HTTP request log is missing; cannot classify download batch POSTs"
    )
    measured = {str(oid) for oid in oids}
    assert measured, "measured oid set is empty"
    download_lists: list[set[str]] = []
    for rec in records:
        if rec.method != "POST" or not _is_objects_batch_path(rec.path):
            continue
        try:
            body = json.loads(rec.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AssertionError(
                f"objects-batch POST body is not JSON: {rec.body!r} ({exc})"
            ) from exc
        if not isinstance(body, dict):
            raise AssertionError(
                f"objects-batch POST JSON is not an object: {body!r}"
            )
        operation = str(body.get("operation") or "")
        if operation != "download":
            continue
        raw_objects = body.get("objects")
        assert isinstance(raw_objects, list), (
            f"download batch POST has no objects list: {body!r}"
        )
        listed: set[str] = set()
        for item in raw_objects:
            assert isinstance(item, dict), (
                f"download batch object is not an object: {item!r}"
            )
            oid = str(item.get("oid") or "")
            assert oid, f"download batch object has no oid: {item!r}"
            listed.add(oid)
        download_lists.append(listed)
        inter = listed & measured
        if inter:
            assert inter == measured, (
                "an intersecting download batch POST listed a proper "
                f"subset of measured oids: listed∩measured={sorted(inter)!r} "
                f"measured={sorted(measured)!r} listed={sorted(listed)!r}"
            )
    assert download_lists, (
        "no download objects-batch POST; "
        f"records={[(r.method, r.path) for r in records]!r}"
    )
    full = [listed for listed in download_lists if measured <= listed]
    assert full, (
        "no download batch POST listed the full measured oid set "
        f"{sorted(measured)!r}; lists={[sorted(s) for s in download_lists]!r}"
    )
    return download_lists


def require_gets_of_action_paths(
    records: list[RecordedHttpExchange] | None,
    paths: Sequence[str],
) -> list[RecordedHttpExchange]:
    """Require a GET of each action path. Does not assert header forwarding."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify GETs of action paths"
    )
    wanted = [_request_path(path) for path in paths]
    assert wanted, "action path list is empty"
    found: list[RecordedHttpExchange] = []
    missing: list[str] = []
    for want in wanted:
        gets = [
            rec
            for rec in records
            if rec.method == "GET" and _request_path(rec.path) == want
        ]
        if not gets:
            missing.append(want)
            continue
        found.append(gets[0])
    assert not missing, (
        f"no GET of action path(s) {missing!r}; "
        f"records={[(r.method, r.path) for r in records]!r}"
    )
    return found


def assert_gets_of_action_paths(
    records: list[RecordedHttpExchange] | None,
    paths: Sequence[str],
) -> list[RecordedHttpExchange]:
    """Require a GET of each action path.

    Same contract as ``require_gets_of_action_paths``. The name is the
    verdict the suite-bailout audit can see: a fetch that never GETs
    the action path has not downloaded.
    """
    return require_gets_of_action_paths(records, paths)


def json_plan_remainder(
    result: RunResult, *, strip: Sequence[str]
) -> str:
    """Return covariate-stripped JSON plan text from caller-visible output.

    Unparseable JSON is a hard failure, never an empty plan.
    """
    value = extract_json_listing(result)
    tokens = json_walk_keys_and_strings(value)
    text = "\n".join(tokens)
    return _strip_unrelated_tokens(text, strip)


def require_json_plan_stable_unlike(
    stable_a: RunResult,
    stable_b: RunResult,
    unlike: RunResult,
) -> tuple[object, object]:
    """Require a parseable JSON plan that is stable, then unlike another plan.

    All three runs must succeed and emit parseable JSON. The two *stable_*
    observations must be equal as JSON values, including numeric and
    boolean fields — incidental per-run strings are not a transfer plan.
    *unlike* must differ from that stable value. Distinguishability is
    not restricted to object keys and string values.
    """
    require_success(stable_a)
    require_success(stable_b)
    require_success(unlike)
    plan_a = extract_json_listing(stable_a)
    plan_b = extract_json_listing(stable_b)
    plan_unlike = extract_json_listing(unlike)
    assert plan_a == plan_b, (
        "JSON transfer plan was not stable across two observations at "
        f"the same occupancy: {plan_a!r} vs {plan_b!r}"
    )
    assert plan_unlike != plan_a, (
        "JSON transfer plans were not distinguishable from a stable "
        f"baseline at the same occupancy: {plan_a!r} vs {plan_unlike!r}"
    )
    return plan_a, plan_unlike


def assert_json_plan_stable_unlike(
    stable_a: RunResult,
    stable_b: RunResult,
    unlike: RunResult,
) -> tuple[object, object]:
    """Require a stable JSON plan that is unlike another plan.

    Same contract as ``require_json_plan_stable_unlike``. The name is
    the verdict the suite-bailout audit can see: a plan that does not
    distinguish the unlike arm at the same occupancy is not a transfer
    plan.
    """
    return require_json_plan_stable_unlike(stable_a, stable_b, unlike)


def read_git_orbulk_hook_bodies_at(
    ws: Workspace, cwd: str | Path
) -> dict[str, str]:
    """Read the four hook files of the repository at *cwd*.

    Each body must invoke Git Orbulk. A missing or non-file path is a hard
    failure, not an empty hook.
    """
    hooks = git_dir_at(ws, cwd) / "hooks"
    bodies: dict[str, str] = {}
    for hook_type in HOOK_TYPES:
        path = hooks / hook_type
        try:
            exists = path.exists()
        except OSError as exc:
            raise AssertionError(
                f"cannot stat hook {hook_type} at {path}: {exc}"
            ) from exc
        assert exists, f"{hook_type} hook is missing at {path}"
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(
                f"cannot stat hook {hook_type} at {path}: {exc}"
            ) from exc
        assert is_file, (
            f"{hook_type} hook exists but is not a regular file: {path}"
        )
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AssertionError(
                f"cannot read hook {hook_type} at {path}: {exc}"
            ) from exc
        bodies[hook_type] = require_hook_invokes_git_orbulk(body)
    return bodies


def require_hooks_absent_at(ws: Workspace, cwd: str | Path) -> None:
    """Require no Git-Orbulk-named hook file exists in the repository at *cwd*.

    A missing path, or a non-file path (for example a blocking directory),
    is classified absence of a Git Orbulk hook file. A regular file that
    names Git Orbulk is a hard failure.
    """
    hooks = git_dir_at(ws, cwd) / "hooks"
    for hook_type in HOOK_TYPES:
        path = hooks / hook_type
        try:
            exists = path.exists()
        except OSError as exc:
            raise AssertionError(
                f"cannot stat hook {hook_type} at {path}: {exc}"
            ) from exc
        if not exists:
            continue
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(
                f"cannot stat hook {hook_type} at {path}: {exc}"
            ) from exc
        if not is_file:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AssertionError(
                f"cannot read hook {hook_type} at {path}: {exc}"
            ) from exc
        assert not _names_git_orbulk_product(body), (
            f"{hook_type} hook at {path} still names Git Orbulk: {body!r}"
        )


def configure_recentness(ws: Workspace, *, ref_days: int) -> None:
    """Setup: set the recent-refs window and disable always-recent."""
    require_git_config_set(
        ws, "lfs.fetchrecentrefsdays", str(ref_days), local=True
    )
    require_git_config_set(ws, "lfs.fetchrecentcommitsdays", "0", local=True)
    require_git_config_set(ws, "lfs.fetchrecentalways", "false", local=True)


# ---------------------------------------------------------------------------
# F09: push / pre-push observation (new names only)
# ---------------------------------------------------------------------------


class StoringBatchServer:
    """Loopback batch+basic fixture that serves only bytes it was PUT."""

    def __init__(
        self,
        *,
        url: str,
        records: list[RecordedHttpExchange],
        stored: dict[str, bytes],
        header_name: str,
        header_value: str,
    ) -> None:
        self.url = url
        self.records = records
        self.stored = stored
        self.header_name = header_name
        self.header_value = header_value


class ForeignLockServer:
    """Reachable batch+basic fixture that reports a foreign lock path."""

    def __init__(
        self,
        *,
        url: str,
        records: list[RecordedHttpExchange],
        header_name: str,
        header_value: str,
    ) -> None:
        self.url = url
        self.records = records
        self.header_name = header_name
        self.header_value = header_value


def set_lfs_endpoint(ws: Workspace, url: str) -> None:
    """Setup: SET lfs.url and short transfer timeouts. Does not add origin."""
    require_git_config_set(ws, "lfs.url", url, local=True)
    require_git_config_set(ws, "lfs.transfer.maxretries", "1", local=True)
    require_git_config_set(ws, "lfs.transfer.maxretrydelay", "0", local=True)
    require_git_config_set(ws, "lfs.dialtimeout", "1", local=True)


def init_bare_git_remote(ws: Workspace, rel: str) -> Path:
    """Create a bare Git repository under *rel*. Failure is not absence."""
    assert rel, "bare remote relative path is empty"
    dest = ws.resolve(rel)
    dest.mkdir(parents=True, exist_ok=True)
    result = ws.git(["init", "--bare", "-b", "main", str(dest)])
    assert result.returncode == 0, (
        f"git init --bare {rel!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return dest


def read_ref(
    ws: Workspace, ref: str, *, cwd: str | Path | None = None
) -> str:
    """Return the SHA of *ref*. A failed rev-parse is not an empty SHA."""
    assert ref, "ref name is empty"
    result = ws.git(["rev-parse", "--verify", ref], cwd=cwd)
    assert result.returncode == 0, (
        f"git rev-parse --verify {ref!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    sha = result.stdout_text.strip()
    assert sha, f"git rev-parse --verify {ref!r} produced no sha"
    return sha


def require_ref_at(
    ws: Workspace,
    ref: str,
    sha: str,
    *,
    cwd: str | Path | None = None,
) -> str:
    """Require *ref* currently names *sha*."""
    observed = read_ref(ws, ref, cwd=cwd)
    assert observed == sha, (
        f"{ref!r} is {observed!r}, expected {sha!r}"
    )
    return observed


def set_remote_tracking(
    ws: Workspace, remote: str, name: str, sha: str
) -> str:
    """Plant ``refs/remotes/<remote>/<name>`` at *sha*. Non-zero is not planted."""
    assert remote and name and sha, (
        f"set_remote_tracking requires remote, name, and sha "
        f"(got {remote!r} {name!r} {sha!r})"
    )
    ref = f"refs/remotes/{remote}/{name}"
    result = ws.git(["update-ref", ref, sha])
    assert result.returncode == 0, (
        f"git update-ref {ref!r} {sha!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return ref


def git_zero_oid() -> str:
    """Git's all-zero object id used on delete pre-push stdin lines."""
    return "0" * 40


def pre_push_stdin(
    *,
    local_ref: str,
    local_sha: str,
    remote_ref: str,
    remote_sha: str,
) -> str:
    """One Git pre-push stdin line (local ref, local sha, remote ref, remote sha)."""
    assert local_ref and local_sha and remote_ref and remote_sha, (
        "pre_push_stdin requires all four fields"
    )
    return f"{local_ref} {local_sha} {remote_ref} {remote_sha}\n"


def skip_push_environment() -> dict[str, str]:
    """Environment mapping that makes the pre-push hook do nothing."""
    return {"GIT_ORBULK_SKIP_PUSH": "1"}


def disable_lock_verification(ws: Workspace) -> None:
    """Setup: turn lock verification off. Does not assert output."""
    require_git_config_set(ws, "lfs.locksverify", "false", local=True)


def enable_lock_verification(ws: Workspace) -> None:
    """Setup: turn lock verification on. Does not assert output."""
    require_git_config_set(ws, "lfs.locksverify", "true", local=True)


def git_state_sha_tokens(
    ws: Workspace, *, cwd: str | Path | None = None
) -> list[str]:
    """Git SHA tokens in this layout (HEAD, refs, rev-list). Git non-zero fails.

    Also includes prefixes of length 7+ that uniquely identify one collected
    SHA, so a dump of a tracking abbreviation is stripped as a covariate.
    """
    collected: list[str] = []
    head = ws.git(["rev-parse", "HEAD"], cwd=cwd)
    assert head.returncode == 0, (
        f"git rev-parse HEAD failed (exit {head.returncode}): "
        f"{head.stderr_text}"
    )
    head_sha = head.stdout_text.strip()
    assert head_sha, "git rev-parse HEAD produced no sha"
    collected.append(head_sha)
    shown = ws.git(["show-ref", "--head"], cwd=cwd)
    assert shown.returncode == 0, (
        f"git show-ref --head failed (exit {shown.returncode}): "
        f"{shown.stderr_text}"
    )
    for line in shown.stdout_text.splitlines():
        parts = line.split()
        if parts:
            collected.append(parts[0])
    listed = ws.git(["rev-list", "--all"], cwd=cwd)
    assert listed.returncode == 0, (
        f"git rev-list --all failed (exit {listed.returncode}): "
        f"{listed.stderr_text}"
    )
    collected.extend(listed.stdout_text.split())
    unique: list[str] = []
    seen: set[str] = set()
    for sha in collected:
        item = sha.strip().casefold()
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    assert unique, "no Git SHA tokens in this layout"
    tokens = list(unique)
    for sha in unique:
        for length in range(7, len(sha)):
            prefix = sha[:length]
            hits = [other for other in unique if other.startswith(prefix)]
            if len(hits) == 1:
                tokens.append(prefix)
    return tokens


def dry_run_remainder(visible: str, *, strip: Sequence[str]) -> str:
    """Delete *strip* covariates from already-read caller-visible text.

    Long tokens (paths, URLs, payloads, full Git SHAs) are substring-removed.
    Shorter hex prefixes are removed as whole words so they cannot nibble a
    64-hex object-id designation. Collapses leftover whitespace. Does not
    parse a plan, and does not map an empty remainder to a sentinel.
    """
    long_tokens: list[str] = []
    short_hex: list[str] = []
    for item in strip:
        if not item:
            continue
        text = str(item)
        hexish = all(char in "0123456789abcdef" for char in text.casefold())
        if hexish and 7 <= len(text) < 40:
            short_hex.append(text)
        else:
            long_tokens.append(text)
    remainder = _strip_unrelated_tokens(visible, long_tokens)
    for item in sorted(short_hex, key=len, reverse=True):
        remainder = _strip_whole_word(remainder, item)
    return " ".join(remainder.split())


def require_dry_run_remainder_stable_unlike(
    stable_a: str,
    stable_b: str,
    *unlike: str,
) -> str:
    """Require a designation remainder that is stable, then unlike each other.

    The two *stable_* remainders must be equal — incidental per-run chatter
    (a timestamp, request id, or other per-run token) is not a designation of
    the pending object. A non-empty stable remainder is required: after
    covariates are stripped, a designation of that pending set must remain.
    Each *unlike* remainder must differ from that stable value. Does not parse
    a plan, pin wording, or close a token set.
    """
    assert unlike, "need at least one unlike remainder"
    assert stable_a, (
        "dry-run remainder vanished after covariate stripping; no "
        "designation of the pending object remained"
    )
    assert stable_a == stable_b, (
        "dry-run remainder was not stable across two observations of the "
        f"same pending set: {stable_a!r} vs {stable_b!r}"
    )
    for other in unlike:
        assert other != stable_a, (
            "dry-run remainder was not distinguishable from a different "
            "pending set after covariate stripping: "
            f"{stable_a!r} vs {other!r}"
        )
    return stable_a


def assert_dry_run_remainder_stable_unlike(
    stable_a: str,
    stable_b: str,
    *unlike: str,
) -> str:
    """Require a stable dry-run designation unlike another remainder.

    Same contract as ``require_dry_run_remainder_stable_unlike``. The name
    is the verdict the suite-bailout audit can see: uniqueness-only leftovers
    are not a designation of the pending object.
    """
    return require_dry_run_remainder_stable_unlike(
        stable_a, stable_b, *unlike
    )


def require_listing_remainder_stable_unlike(
    stable_a: str,
    stable_b: str,
    unlike_a: str,
    unlike_b: str,
) -> tuple[str, str]:
    """Require two listing remainders that are each stable, then unlike.

    Each pair is two observations of the same ownership state. Equality
    inside a pair means incidental per-run chatter (a timestamp, request
    id, or other per-run token) is not the contrast. The two states must
    still differ. Does not pin mark characters or field names.
    """
    assert stable_a == stable_b, (
        "listing remainder was not stable across two observations of the "
        f"same ownership state: {stable_a!r} vs {stable_b!r}"
    )
    assert unlike_a == unlike_b, (
        "listing remainder was not stable across two observations of the "
        f"same ownership state: {unlike_a!r} vs {unlike_b!r}"
    )
    assert stable_a != unlike_a, (
        "listing remainders were not distinguishable after stripping "
        f"identity covariates: {stable_a!r} vs {unlike_a!r}"
    )
    return stable_a, unlike_a


def assert_listing_remainder_stable_unlike(
    stable_a: str,
    stable_b: str,
    unlike_a: str,
    unlike_b: str,
) -> tuple[str, str]:
    """Require a stable listing remainder unlike another stable remainder.

    Same contract as ``require_listing_remainder_stable_unlike``. The name
    is the verdict the suite-bailout audit can see: a per-run leftover is
    not an ownership mark.
    """
    return require_listing_remainder_stable_unlike(
        stable_a, stable_b, unlike_a, unlike_b
    )


def _is_locks_verify_path(path: str) -> bool:
    cleaned = _request_path(path).rstrip("/")
    return cleaned == "/locks/verify" or cleaned.endswith("/locks/verify")


def _batch_headers_dict(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in handler.headers.items():
        out[str(key)] = str(value)
    return out


def _origin_for_handler(handler: BaseHTTPRequestHandler) -> str:
    return f"http://{handler.headers.get('Host') or '127.0.0.1'}"


def _rewrite_placeholder_hrefs(
    objects: list[dict[str, object]], origin: str
) -> None:
    for item in objects:
        actions = item.get("actions")
        if not isinstance(actions, dict):
            continue
        for _name, action in actions.items():
            if not isinstance(action, dict):
                continue
            href = str(action.get("href") or "")
            if href.startswith("http://placeholder"):
                action["href"] = origin + href[len("http://placeholder") :]


@contextmanager
def storing_batch_server() -> Iterator[StoringBatchServer]:
    """Loopback Git Orbulk batch + basic transfer that stores PUT bytes.

    Download GET returns only objects that were previously PUT. An oid
    that was never PUT is a download-batch object error, not pre-seeded
    content. Not a rewrite of conforming_batch_server.
    """
    records: list[RecordedHttpExchange] = []
    stored: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()

    def _ensure_action(oid: str) -> str:
        if oid not in action_paths:
            path = f"/obj_{token()}"
            action_paths[oid] = path
            path_to_oid[path] = oid
        return action_paths[oid]

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = _batch_headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            if path in path_to_oid and self.command == "PUT":
                self._serve_put(path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                item: dict[str, object] = {
                    "oid": oid,
                    "size": size,
                    "authenticated": True,
                }
                if operation == "download":
                    if oid not in stored:
                        item["error"] = {"code": 404, "message": "unavailable"}
                    else:
                        href = "http://placeholder" + _ensure_action(oid)
                        item["actions"] = {
                            "download": {
                                "href": href,
                                "header": {hdr_name: hdr_value},
                            }
                        }
                else:
                    href = "http://placeholder" + _ensure_action(oid)
                    item["actions"] = {
                        "upload": {
                            "href": href,
                            "header": {hdr_name: hdr_value},
                        }
                    }
                reply_objects.append(item)
            origin = _origin_for_handler(self)
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            with lock:
                data = stored.get(oid)
            if data is None:
                _send_bytes(self, 404, b"")
                return
            _send_bytes(
                self,
                200,
                data,
                content_type="application/octet-stream",
            )

        def _serve_put(self, path: str, body: bytes) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            with lock:
                stored[oid] = body
            _send_bytes(self, 200, b"")

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield StoringBatchServer(
            url=svc.url,
            records=records,
            stored=stored,
            header_name=hdr_name,
            header_value=hdr_value,
        )


@contextmanager
def foreign_lock_on_path_server(
    path: str | None,
    payloads: Sequence[bytes],
) -> Iterator[ForeignLockServer]:
    """Reachable batch+basic fixture; lock-verify reports a foreign lock.

    *path* is the repository-relative path held by someone else, or None
    for no foreign lock. Assertions must not pin the verify URL. PUT of
    registered payload bytes is still the transfer observation.
    """
    payload_list = list(payloads)
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()
    theirs: list[dict[str, object]] = []
    if path is not None:
        theirs = [
            {
                "id": f"lock_{token()}",
                "path": path,
                "owner": {"name": f"other_{token()}"},
            }
        ]

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            req_path = _request_path(self.path)
            headers = _batch_headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=req_path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_locks_verify_path(req_path) and self.command == "POST":
                payload = json.dumps({"ours": [], "theirs": theirs}).encode(
                    "utf-8"
                )
                _send_bytes(self, 200, payload, content_type=media)
                return
            if _is_objects_batch_path(req_path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if req_path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(req_path)
                return
            if req_path in path_to_oid and self.command == "PUT":
                self._serve_put(req_path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                item: dict[str, object] = {
                    "oid": oid,
                    "size": size,
                    "authenticated": True,
                }
                href_oid = oid if oid in action_paths else None
                if href_oid is None and action_paths:
                    href_oid = next(iter(action_paths))
                if href_oid is not None:
                    href = "http://placeholder" + action_paths[href_oid]
                    action = {
                        "href": href,
                        "header": {hdr_name: hdr_value},
                    }
                    actions: dict[str, object] = {}
                    if operation == "download":
                        actions["download"] = action
                    else:
                        actions["upload"] = action
                    item["actions"] = actions
                reply_objects.append(item)
            origin = _origin_for_handler(self)
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            _send_bytes(
                self,
                200,
                by_oid[oid],
                content_type="application/octet-stream",
            )

        def _serve_put(self, path: str, body: bytes) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            expected = by_oid[oid]
            if body != expected:
                _send_bytes(self, 400, b"")
                return
            _send_bytes(self, 200, b"")

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield ForeignLockServer(
            url=svc.url,
            records=records,
            header_name=hdr_name,
            header_value=hdr_value,
        )


# ---------------------------------------------------------------------------
# F10: file locking API fixture and observation helpers (new names only)
# ---------------------------------------------------------------------------

_LOCKED_AT = "2001-01-01T00:00:00Z"


class LockingApiServer:
    """Loopback locking API plus optional batch+basic transfer.

    Create, list, unlock, and verify are first-class. A directory path
    that is POSTed is recorded as an ordinary lock. A second create for
    an existing path is a conflict and does not add a second lock.
    """

    def __init__(
        self,
        *,
        url: str,
        records: list[RecordedHttpExchange],
        state: dict[str, object],
        header_name: str,
        header_value: str,
        current_owner: str,
        foreign_owner: str,
        lock: threading.Lock,
    ) -> None:
        self.url = url
        self.records = records
        self.header_name = header_name
        self.header_value = header_value
        self.current_owner = current_owner
        self.foreign_owner = foreign_owner
        self._state = state
        self._lock = lock

    def _table(self) -> dict[str, dict[str, object]]:
        table = self._state.get("locks")
        assert isinstance(table, dict), (
            "locking fixture lock table is missing; server is not ready"
        )
        return table

    def held_paths(self) -> list[str]:
        with self._lock:
            return list(self._table().keys())

    def lock_id_for(self, path: str) -> str:
        with self._lock:
            rec = self._table().get(path)
        assert rec is not None, (
            f"fixture does not hold a lock for {path!r}; "
            f"held={self.held_paths()!r}"
        )
        lock_id = str(rec["id"])
        assert lock_id, f"fixture lock for {path!r} has an empty id"
        return lock_id

    def owner_for(self, path: str) -> str:
        with self._lock:
            rec = self._table().get(path)
        assert rec is not None, (
            f"fixture does not hold a lock for {path!r}; "
            f"held={self.held_paths()!r}"
        )
        owner = str(rec["owner"])
        assert owner, f"fixture lock for {path!r} has an empty owner"
        return owner

    def inject_foreign_lock(self, path: str) -> str:
        """Plant a lock owned by someone other than the current user."""
        assert path, "inject_foreign_lock path is empty"
        lock_id = f"lk_{token()}"
        rec = {
            "id": lock_id,
            "path": path,
            "owner": self.foreign_owner,
            "ours": False,
            "locked_at": _LOCKED_AT,
        }
        with self._lock:
            table = self._table()
            assert path not in table, (
                f"cannot inject foreign lock; path {path!r} already held"
            )
            table[path] = rec
        return lock_id

    def conflict_create_paths(self) -> list[str]:
        with self._lock:
            raw = self._state.get("conflict_creates")
        assert isinstance(raw, list), (
            "locking fixture conflict-create log is missing; "
            "server is not ready"
        )
        return [str(item) for item in raw]

    def verify_count(self) -> int:
        with self._lock:
            raw = self._state.get("verify_count")
        assert raw is not None, (
            "locking fixture verify counter is missing; server is not ready"
        )
        return int(raw)


def _is_locks_collection_path(path: str) -> bool:
    cleaned = _request_path(path).rstrip("/")
    return cleaned == "/locks" or cleaned.endswith("/locks")


def _is_locks_unlock_path(path: str) -> bool:
    cleaned = _request_path(path).rstrip("/")
    return "/locks/" in cleaned and cleaned.endswith("/unlock")


def _lock_id_from_unlock_path(path: str) -> str:
    cleaned = _request_path(path).rstrip("/")
    parts = cleaned.split("/")
    for index, part in enumerate(parts):
        if (
            part == "locks"
            and index + 2 < len(parts)
            and parts[index + 2] == "unlock"
        ):
            lock_id = parts[index + 1]
            assert lock_id, f"unlock path has an empty lock id: {path!r}"
            return lock_id
    raise AssertionError(f"cannot classify unlock lock id from {path!r}")


def _lock_object_payload(rec: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": rec["id"],
        "path": rec["path"],
        "locked_at": rec["locked_at"],
        "owner": {"name": rec["owner"]},
    }


@contextmanager
def locking_api_server(
    *,
    payloads: Sequence[bytes] | None = None,
    lock_routes: str = "full",
) -> Iterator[LockingApiServer]:
    """Loopback Git Orbulk locking API, optionally with batch+basic transfer.

    *lock_routes*: ``full`` serves create/list/unlock/verify; ``absent``
    returns 404 on those routes; ``unauthorized`` returns 401. Directory
    create POSTs are stored as ordinary locks. Conflict creates keep a
    single lock and are recorded as conflict-class requests.
    """
    assert lock_routes in ("full", "absent", "unauthorized"), (
        f"lock_routes must be full, absent, or unauthorized, got {lock_routes!r}"
    )
    payload_list = list(payloads or ())
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    gate = threading.Lock()
    media = contract_git_orbulk_json_media_type()
    current_owner = f"own_{token()}"
    foreign_owner = f"oth_{token()}"
    state: dict[str, object] = {
        "locks": {},
        "conflict_creates": [],
        "verify_count": 0,
    }

    def _lock_json_bytes(body: dict[str, object]) -> bytes:
        return json.dumps(body).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            req_path = _request_path(self.path)
            headers = _batch_headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=self.path,
                headers=headers,
                body=body,
            )
            with gate:
                records.append(rec)
            if _is_objects_batch_path(req_path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if req_path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(req_path)
                return
            if req_path in path_to_oid and self.command == "PUT":
                self._serve_put(req_path, body)
                return
            if (
                _is_locks_verify_path(req_path)
                or _is_locks_collection_path(req_path)
                or _is_locks_unlock_path(req_path)
            ):
                self._serve_locking(req_path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_locking(self, req_path: str, body: bytes) -> None:
            if lock_routes == "absent":
                payload = _lock_json_bytes({"message": "not found"})
                _send_bytes(self, 404, payload, content_type=media)
                return
            if lock_routes == "unauthorized":
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="lfs"')
                payload = _lock_json_bytes({"message": "unauthorized"})
                self.send_header("Content-Type", media)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                return
            if _is_locks_verify_path(req_path) and self.command == "POST":
                self._serve_verify()
                return
            if _is_locks_collection_path(req_path) and self.command == "POST":
                self._serve_create(body)
                return
            if _is_locks_collection_path(req_path) and self.command == "GET":
                self._serve_list()
                return
            if _is_locks_unlock_path(req_path) and self.command == "POST":
                self._serve_unlock(req_path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_create(self, body: bytes) -> None:
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            path = str(parsed.get("path") or "")
            if not path:
                _send_bytes(self, 400, b"")
                return
            with gate:
                table = state["locks"]
                assert isinstance(table, dict)
                existing = table.get(path)
                if existing is not None:
                    conflicts = state["conflict_creates"]
                    assert isinstance(conflicts, list)
                    conflicts.append(path)
                    payload = _lock_json_bytes(
                        {
                            "lock": _lock_object_payload(existing),
                            "message": "already locked",
                        }
                    )
                    _send_bytes(self, 409, payload, content_type=media)
                    return
                rec = {
                    "id": f"lk_{token()}",
                    "path": path,
                    "owner": current_owner,
                    "ours": True,
                    "locked_at": _LOCKED_AT,
                }
                table[path] = rec
            payload = _lock_json_bytes({"lock": _lock_object_payload(rec)})
            _send_bytes(self, 201, payload, content_type=media)

        def _serve_list(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            path_filter = query.get("path", [None])[0]
            id_filter = query.get("id", [None])[0]
            with gate:
                table = state["locks"]
                assert isinstance(table, dict)
                items = list(table.values())
            matched: list[dict[str, object]] = []
            for rec in items:
                if path_filter is not None and str(rec["path"]) != path_filter:
                    continue
                if id_filter is not None and str(rec["id"]) != id_filter:
                    continue
                matched.append(_lock_object_payload(rec))
            payload = _lock_json_bytes({"locks": matched})
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_verify(self) -> None:
            with gate:
                state["verify_count"] = int(state["verify_count"]) + 1
                table = state["locks"]
                assert isinstance(table, dict)
                items = list(table.values())
            ours = [
                _lock_object_payload(rec) for rec in items if rec["ours"]
            ]
            theirs = [
                _lock_object_payload(rec)
                for rec in items
                if not rec["ours"]
            ]
            payload = _lock_json_bytes({"ours": ours, "theirs": theirs})
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_unlock(self, req_path: str, body: bytes) -> None:
            lock_id = _lock_id_from_unlock_path(req_path)
            force = False
            if body:
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    _send_bytes(self, 400, b"")
                    return
                if isinstance(parsed, dict):
                    force = bool(parsed.get("force"))
            with gate:
                table = state["locks"]
                assert isinstance(table, dict)
                found: dict[str, object] | None = None
                found_path: str | None = None
                for path, rec in table.items():
                    if str(rec["id"]) == lock_id:
                        found = rec
                        found_path = path
                        break
                if found is None or found_path is None:
                    payload = _lock_json_bytes({"message": "not found"})
                    _send_bytes(self, 404, payload, content_type=media)
                    return
                if not found["ours"] and not force:
                    payload = _lock_json_bytes(
                        {
                            "lock": _lock_object_payload(found),
                            "message": "not owner",
                        }
                    )
                    _send_bytes(self, 403, payload, content_type=media)
                    return
                del table[found_path]
            payload = _lock_json_bytes({"lock": _lock_object_payload(found)})
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                item: dict[str, object] = {
                    "oid": oid,
                    "size": size,
                    "authenticated": True,
                }
                href_oid = oid if oid in action_paths else None
                if href_oid is None and action_paths:
                    href_oid = next(iter(action_paths))
                if href_oid is not None:
                    href = "http://placeholder" + action_paths[href_oid]
                    action = {
                        "href": href,
                        "header": {hdr_name: hdr_value},
                    }
                    actions: dict[str, object] = {}
                    if operation == "download":
                        actions["download"] = action
                    else:
                        actions["upload"] = action
                    item["actions"] = actions
                reply_objects.append(item)
            origin = _origin_for_handler(self)
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            _send_bytes(
                self,
                200,
                by_oid[oid],
                content_type="application/octet-stream",
            )

        def _serve_put(self, path: str, body: bytes) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            expected = by_oid[oid]
            if body != expected:
                _send_bytes(self, 400, b"")
                return
            _send_bytes(self, 200, b"")

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield LockingApiServer(
            url=svc.url,
            records=records,
            state=state,
            header_name=hdr_name,
            header_value=hdr_value,
            current_owner=current_owner,
            foreign_owner=foreign_owner,
            lock=gate,
        )


def require_server_holds_lock(server: LockingApiServer, path: str) -> str:
    """Require the fixture lock table holds *path*. Missing is not absence."""
    assert server is not None, (
        "locking fixture is missing; cannot classify a held lock"
    )
    assert path, "lock path is empty"
    lock_id = server.lock_id_for(path)
    print(f"server holds {path!r} id={lock_id!r}")
    return lock_id


def assert_server_holds_lock(server: LockingApiServer, path: str) -> str:
    """Require the fixture lock table holds *path*.

    Same contract as ``require_server_holds_lock``. The name is the
    verdict the suite-bailout audit can see: a lock command that never
    creates a server-side lock has not locked.
    """
    return require_server_holds_lock(server, path)


def require_server_lacks_lock(server: LockingApiServer, path: str) -> None:
    """Require the fixture lock table does not hold *path*."""
    assert server is not None, (
        "locking fixture is missing; cannot classify a missing lock"
    )
    assert path, "lock path is empty"
    held = server.held_paths()
    assert path not in held, (
        f"fixture still holds a lock for {path!r}: {held!r}"
    )


def assert_server_lacks_lock(server: LockingApiServer, path: str) -> None:
    """Require the fixture lock table does not hold *path*.

    Same contract as ``require_server_lacks_lock``. The name is the
    verdict the suite-bailout audit can see: an unlock that leaves the
    path held has not unlocked.
    """
    require_server_lacks_lock(server, path)


def require_locking_create_conflict(
    server: LockingApiServer, path: str
) -> None:
    """Require a create request for *path* was answered as a conflict."""
    assert server is not None, (
        "locking fixture is missing; cannot classify a conflict create"
    )
    conflicts = server.conflict_create_paths()
    assert path in conflicts, (
        "fixture recorded no conflict-class create for "
        f"{path!r}; conflicts={conflicts!r}"
    )


def require_locking_verify_received(server: LockingApiServer) -> int:
    """Require at least one verify-class exchange. Missing is not zero."""
    assert server is not None, (
        "locking fixture is missing; cannot classify a verify exchange"
    )
    count = server.verify_count()
    assert count > 0, (
        "fixture recorded no verify-class exchange"
    )
    return count


def require_file_read_only(path: str | Path) -> None:
    """Require *path* exists as a file with owner-write disabled.

    Classifies from mode bits, not ``os.access`` (root can still write
    a 0444 file). Missing or unreadable is a hard failure, not writable.
    """
    target = Path(path)
    try:
        st = target.stat()
    except FileNotFoundError:
        raise AssertionError(
            f"path is missing; cannot classify read-only: {target}"
        ) from None
    except OSError as exc:
        raise AssertionError(f"cannot stat {target}: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise AssertionError(f"not a regular file: {target}")
    assert (st.st_mode & 0o222) == 0, (
        f"expected read-only (no write bits), mode={oct(st.st_mode)} "
        f"path={target}"
    )


def assert_file_read_only(path: str | Path) -> None:
    """Require *path* exists as a file with owner-write disabled.

    Same contract as ``require_file_read_only``. The name is the verdict
    the suite-bailout audit can see: an unlocked lockable file that stays
    writable has not been set read-only.
    """
    require_file_read_only(path)


def require_file_writable(path: str | Path) -> None:
    """Require *path* exists as a file with owner-write enabled."""
    target = Path(path)
    try:
        st = target.stat()
    except FileNotFoundError:
        raise AssertionError(
            f"path is missing; cannot classify writable: {target}"
        ) from None
    except OSError as exc:
        raise AssertionError(f"cannot stat {target}: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise AssertionError(f"not a regular file: {target}")
    assert (st.st_mode & 0o200) != 0, (
        f"expected owner-writable, mode={oct(st.st_mode)} path={target}"
    )


def assert_file_writable(path: str | Path) -> None:
    """Require *path* exists as a file with owner-write enabled.

    Same contract as ``require_file_writable``. The name is the verdict
    the suite-bailout audit can see: a locked lockable file that stays
    read-only has not become writable.
    """
    require_file_writable(path)


def make_file_writable(path: str | Path) -> None:
    """Set owner-write on an existing file. Failure is not already-writable."""
    target = Path(path)
    try:
        st = target.stat()
    except FileNotFoundError:
        raise AssertionError(
            f"cannot make writable; missing: {target}"
        ) from None
    except OSError as exc:
        raise AssertionError(f"cannot stat {target}: {exc}") from exc
    try:
        os.chmod(target, st.st_mode | 0o200)
    except OSError as exc:
        raise AssertionError(f"cannot chmod writable {target}: {exc}") from exc
    require_file_writable(target)


def run_lock(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the lock porcelain with *argv* after the subcommand name."""
    args = ["lock", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def run_unlock(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the unlock porcelain with *argv* after the subcommand name."""
    args = ["unlock", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def run_locks(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the locks porcelain with *argv* after the subcommand name."""
    args = ["locks", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def run_post_checkout(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run post-checkout plumbing with Git hook argv after the name."""
    args = ["post-checkout", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def run_post_commit(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run post-commit plumbing. Git's hook passes no arguments."""
    args = ["post-commit", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def run_post_merge(
    ws: Workspace,
    argv: Sequence[str],
    *,
    via_git: bool = True,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run post-merge plumbing with Git hook argv after the name."""
    args = ["post-merge", *[str(item) for item in argv]]
    if via_git:
        return ws.invoke_via_git(args, env_updates=env_updates)
    return ws.invoke(args, env_updates=env_updates)


def locks_listing_visible(result: RunResult) -> str:
    """Caller-visible locks listing text. Does not map failure to empty."""
    return caller_visible(result)


def json_strings_include(obj: object, token: str) -> list[str]:
    """Require *token* appears in the JSON key/string tree."""
    assert token, "json_strings_include token is empty"
    walked = json_walk_keys_and_strings(obj)
    assert token in walked, (
        f"JSON string tree does not include {token!r}: {walked!r}"
    )
    return walked


def assert_json_strings_include(obj: object, token: str) -> list[str]:
    """Require *token* appears in the JSON key/string tree.

    Same contract as ``json_strings_include``. The name is the verdict
    the suite-bailout audit can see: a JSON listing that omits the locked
    path has not named it.
    """
    return json_strings_include(obj, token)


def strip_listing_covariates(text: str, tokens: Sequence[str]) -> str:
    """Strip URLs, then caller tokens (paths, owners, ids, absolute paths).

    Collapses leftover whitespace. Does not map an empty remainder to a
    sentinel and does not parse a listing.
    """
    urls = _extract_urls(text)
    remainder = _strip_unrelated_tokens(text, [*urls, *[str(t) for t in tokens if t]])
    return " ".join(remainder.split())


def track_lockable(ws: Workspace, glob: str) -> RunResult:
    """Setup: track *glob* with lockable. Does not rewrite track_pattern."""
    result = run_track(ws, ["--lockable", glob])
    require_success(result)
    return result


def unset_lock_verification(ws: Workspace) -> None:
    """Setup: leave locks-verify unset (unknown/prompt). Failure is not unset."""
    value = lookup_git_config(ws, "lfs.locksverify", local=True)
    if value is None:
        return
    result = ws.git(["config", "--local", "--unset", "lfs.locksverify"])
    assert result.returncode == 0, (
        "failed to unset lfs.locksverify "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    leftover = lookup_git_config(ws, "lfs.locksverify", local=True)
    assert leftover is None, (
        f"lfs.locksverify still set after unset: {leftover!r}"
    )


# ---------------------------------------------------------------------------
# F11: status / ls-files inspection (new names only)
# ---------------------------------------------------------------------------


def run_status(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the status porcelain with *argv* after the subcommand name."""
    args = ["status", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def run_ls_files(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the ls-files porcelain with *argv* after the subcommand name."""
    args = ["ls-files", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def configure_current_branch_upstream(ws: Workspace, remote: str) -> str:
    """SET the current branch's remote (and merge) so unpushed can resolve.

    Does not plant a remote-tracking ref and does not rewrite
    ``set_remote_tracking``.
    """
    assert remote, "upstream remote name is empty"
    result = ws.git(["rev-parse", "--abbrev-ref", "HEAD"])
    assert result.returncode == 0, (
        "git rev-parse --abbrev-ref HEAD failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    branch = result.stdout_text.strip()
    assert branch, "current branch name is empty"
    assert branch != "HEAD", (
        "HEAD is detached; cannot SET a current-branch upstream"
    )
    require_git_config_set(
        ws, f"branch.{branch}.remote", remote, local=True
    )
    require_git_config_set(
        ws, f"branch.{branch}.merge", f"refs/heads/{branch}", local=True
    )
    return branch


def named_path_listing_line(
    text: str,
    path: str,
    *,
    other_paths: Sequence[str] = (),
) -> str:
    """Return the unique caller-visible line that names *path*.

    Missing or unreadable classification is a hard failure, never an
    empty line standing in for 'not listed'. A single line that also
    carries another measured path token is unclassified.
    """
    assert path, "named path token is empty"
    lines = [line for line in text.splitlines() if path in line]
    assert lines, (
        f"no default named-path listing line names {path!r}: {text!r}"
    )
    assert len(lines) == 1, (
        f"multiple listing lines name {path!r}: {lines!r}"
    )
    line = lines[0]
    for other in other_paths:
        if not other or other == path:
            continue
        assert other not in line, (
            "one listing line carried two measured path tokens "
            f"{path!r} and {other!r}: {line!r}"
        )
    return line


def json_named_entry(obj: object, path: str) -> object:
    """Return the innermost JSON object whose string tree names *path*.

    Missing is a hard failure, never an empty object. Several matching
    innermost objects cannot be classified.
    """
    assert path, "json named-entry path token is empty"
    found: list[object] = []

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            strings = json_walk_keys_and_strings(value)
            if path in strings:
                child_has = False
                for inner in value.values():
                    if isinstance(inner, (dict, list)) and path in json_walk_keys_and_strings(
                        inner
                    ):
                        child_has = True
                        break
                if not child_has:
                    found.append(value)
            for inner in value.values():
                _walk(inner)
            return
        if isinstance(value, list):
            for inner in value:
                _walk(inner)

    _walk(obj)
    assert found, (
        f"parsed JSON has no named entry whose string tree includes "
        f"{path!r}: {obj!r}"
    )
    assert len(found) == 1, (
        f"multiple JSON named entries include {path!r}: {found!r}"
    )
    return found[0]


def json_named_entry_visible(entry: object) -> str:
    """Serialize a named JSON entry including booleans and numbers.

    Does not walk only keys and strings; a boolean local-store mark
    must remain visible.
    """
    return json.dumps(entry, sort_keys=True)


def extract_json_listing_if_present(result: RunResult) -> object | None:
    """Return a parseable JSON value from caller-visible output, or None.

    ``None`` means no parseable JSON document was present. It is not an
    empty document and is not used on a JSON-only success arm.
    """
    text = listing_visible(result)
    decoder = json.JSONDecoder()
    stripped = text.lstrip()
    if stripped:
        try:
            value, _consumed = decoder.raw_decode(stripped)
            return value
        except json.JSONDecodeError:
            pass
    found: list[object] = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        found.append(value)
    if not found:
        return None
    for value in found:
        if isinstance(value, (dict, list)):
            return value
    return found[0]


def listing_without_json_document(result: RunResult) -> str:
    """Caller-visible listing text with one parseable JSON document removed.

    No parseable JSON is not mapped to an empty listing: the full text
    is returned. A trailing or embedded JSON document is excised so a
    preferred human format can be compared to a JSON-only arm. Does not
    treat missing JSON as a successful suppression.
    """
    text = listing_visible(result)
    decoder = json.JSONDecoder()
    stripped = text.lstrip()
    lead = len(text) - len(stripped)
    if stripped:
        try:
            _value, consumed = decoder.raw_decode(stripped)
            return (text[:lead] + stripped[consumed:]).strip()
        except json.JSONDecodeError:
            pass
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return (text[:index] + text[index + consumed :]).strip()
    return text


def size_dump_strip_tokens(size: int) -> list[str]:
    """Covariate tokens for a known byte length. Not a required rendering."""
    tokens: list[str] = [str(size)]
    for width in (2, 3, 4, 5, 6, 8):
        tokens.append(str(size).rjust(width))
        tokens.append(str(size).rjust(width, "0"))
    units = ("B", "KB", "KiB", "MB", "MiB", "bytes", "byte")
    for unit in units:
        tokens.append(f"{size}{unit}")
        tokens.append(f"{size} {unit}")
        tokens.append(f"{size}{unit.lower()}")
        tokens.append(f"{size} {unit.lower()}")
        tokens.append(f"({size})")
        tokens.append(f"({size}{unit})")
        tokens.append(f"({size} {unit})")
        tokens.append(f"({size} {unit.lower()})")
    return tokens


def content_dump_strip_tokens(blob: bytes) -> list[str]:
    """Covariate tokens for a known working-tree blob dump. Not required form."""
    assert blob, "content-dump blob is empty"
    tokens: list[str] = []
    hex_lower = blob.hex()
    hex_upper = hex_lower.upper()
    tokens.append(hex_lower)
    tokens.append(hex_upper)
    for length in (8, 12, 16, 24, 32):
        if len(hex_lower) >= length:
            tokens.append(hex_lower[:length])
            tokens.append(hex_upper[:length])
    encoded = base64.b64encode(blob).decode("ascii")
    tokens.append(encoded)
    for length in (8, 12, 16, 24, 32):
        if len(encoded) >= length:
            tokens.append(encoded[:length])
    tokens.append(hashlib.md5(blob).hexdigest())
    tokens.append(hashlib.sha1(blob).hexdigest())
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    tokens.append(str(crc))
    tokens.append(format(crc, "x"))
    tokens.append(format(crc, "X"))
    return tokens


def listing_observation_remainder(
    text: str,
    *,
    paths: Sequence[str],
    oids: Sequence[str],
    worktree_blobs: Sequence[bytes],
    pointers: Sequence[bytes] = (),
    sizes: Sequence[int] = (),
    abs_paths: Sequence[str] = (),
) -> str:
    """Strip listing covariates; leftover is the dedicated indication carrier.

    An empty leftover is returned as empty text, never a sentinel.
    """
    tokens: list[str] = []
    for path in paths:
        if path:
            tokens.append(path)
    for abs_path in abs_paths:
        if abs_path:
            tokens.append(abs_path)
    for oid in oids:
        if not oid:
            continue
        tokens.append(oid)
        upper = min(len(oid), 16)
        for length in range(7, upper + 1):
            tokens.append(oid[:length])
    for blob in worktree_blobs:
        try:
            tokens.append(blob.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise AssertionError(
                "working-tree blob is not UTF-8; cannot strip it as an "
                f"input-byte covariate: {exc}"
            ) from exc
        tokens.append(sha256_hex(blob))
        tokens.extend(content_dump_strip_tokens(blob))
    for pointer in pointers:
        try:
            tokens.append(pointer.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise AssertionError(
                "pointer document is not UTF-8; cannot strip it as an "
                f"input-byte covariate: {exc}"
            ) from exc
        tokens.extend(content_dump_strip_tokens(pointer))
    for size in sizes:
        tokens.extend(size_dump_strip_tokens(int(size)))
    return strip_listing_covariates(text, tokens)


# ---------------------------------------------------------------------------
# F12: local object pruning (new names only)
# ---------------------------------------------------------------------------


def run_prune(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the prune porcelain with *argv* after the subcommand name."""
    args = ["prune", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def commit_tracked_payload_dated(
    ws: Workspace, relpath: str, data: bytes, when: str
) -> str:
    """Write, add, and commit *data* at *relpath* with a fixed author/committer date.

    Returns the independent SHA-256. A failed add or commit is not treated
    as a stored object. Does not rewrite ``commit_tracked_payload``.
    """
    assert when, "commit date is empty"
    ws.write(relpath, data)
    digest = sha256_hex(data)
    to_add = [relpath]
    try:
        ws.read_bytes(".gitattributes")
        to_add.append(".gitattributes")
    except FileNotFoundError:
        pass
    added = ws.git(["add", "--", *to_add])
    assert added.returncode == 0, (
        f"git add {to_add!r} failed (exit {added.returncode}): "
        f"{added.stderr_text}"
    )
    committed = ws.git(
        ["commit", "-m", f"add {relpath}"],
        env_updates={
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
        },
    )
    assert committed.returncode == 0, (
        f"git commit {relpath!r} failed "
        f"(exit {committed.returncode}): {committed.stderr_text}"
    )
    return digest


def configured_lfs_store_root(ws: Workspace) -> Path:
    """Local object-store root, honoring a local ``lfs.storage`` setting.

    Git ``--get`` exit 1 (unset) falls back to ``default_lfs_store_root``.
    Any other non-zero is a hard failure, never absence. Does not rewrite
    ``default_lfs_store_root``. Objects under this root still use
    ``sharded_object_rel``.
    """
    raw = lookup_git_config(ws, "lfs.storage", local=True)
    if raw is None:
        return default_lfs_store_root(ws)
    assert raw, "lfs.storage is set but empty"
    path = Path(raw)
    if not path.is_absolute():
        path = (ws.path / path).resolve()
    else:
        path = path.resolve()
    return path


# ---------------------------------------------------------------------------
# F13: object and pointer integrity check (new names only)
# ---------------------------------------------------------------------------


def run_fsck(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the fsck porcelain with *argv* after the subcommand name."""
    args = ["fsck", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def lfs_quarantine_dir(ws: Workspace) -> Path:
    """Repository LFS ``bad`` quarantine directory. Path only."""
    return default_lfs_store_root(ws) / "bad"


def require_quarantined_bytes(ws: Workspace, data: bytes) -> Path:
    """Require the LFS ``bad`` directory exists and holds a file equal to *data*.

    Directory missing, unreadable, or with no matching file is a hard
    failure. Does not require the file name to equal an object id.
    """
    bad = lfs_quarantine_dir(ws)
    try:
        exists = bad.exists()
    except OSError as exc:
        raise AssertionError(
            f"cannot stat quarantine directory {bad}: {exc}"
        ) from exc
    assert exists, f"quarantine directory missing at {bad}"
    try:
        is_dir = bad.is_dir()
    except OSError as exc:
        raise AssertionError(f"cannot stat {bad}: {exc}") from exc
    assert is_dir, f"quarantine path is not a directory: {bad}"
    try:
        names = os.listdir(bad)
    except OSError as exc:
        raise AssertionError(
            f"cannot list quarantine directory {bad}: {exc}"
        ) from exc
    matched: list[Path] = []
    for name in names:
        path = bad / name
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(f"cannot stat {path}: {exc}") from exc
        if not is_file:
            continue
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise AssertionError(f"cannot read {path}: {exc}") from exc
        if body == data:
            matched.append(path)
    assert matched, (
        "no quarantined file equals the expected bytes "
        f"at {bad} (entries={names!r})"
    )
    return matched[0]


def require_not_quarantined_bytes(ws: Workspace, data: bytes) -> None:
    """Require no file in LFS ``bad`` equals *data*.

    A missing ``bad`` directory is classified as not quarantined. Stat
    or listdir failure is a hard failure, never absence.
    """
    bad = lfs_quarantine_dir(ws)
    try:
        exists = bad.exists()
    except OSError as exc:
        raise AssertionError(
            f"cannot stat quarantine directory {bad}: {exc}"
        ) from exc
    if not exists:
        return
    try:
        names = os.listdir(bad)
    except OSError as exc:
        raise AssertionError(
            f"cannot list quarantine directory {bad}: {exc}"
        ) from exc
    for name in names:
        path = bad / name
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(f"cannot stat {path}: {exc}") from exc
        if not is_file:
            continue
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise AssertionError(f"cannot read {path}: {exc}") from exc
        assert body != data, (
            f"bytes unexpectedly present in quarantine at {path}"
        )


def assert_not_quarantined_bytes(ws: Workspace, data: bytes) -> None:
    """Require no file in LFS ``bad`` equals *data*.

    Same contract as ``require_not_quarantined_bytes``. The name is the
    verdict the suite-bailout audit can see: a clean check that still
    quarantined the object has not left occupancy unchanged.
    """
    require_not_quarantined_bytes(ws, data)


def bitflip_stored_object(
    ws: Workspace, oid: str, *, align_mtime_oid: str | None = None
) -> bytes:
    """Flip one bit of the sharded object *oid* and align timestamps.

    Missing or unreadable is a hard failure, not 'already corrupt'.
    After write-back, *oid*'s atime/mtime are set to the stamp taken
    from *align_mtime_oid* before that write (or from *oid* itself when
    no neighbor is given). When a neighbor oid is given, that same stamp
    is applied to the neighbor so the flipped file is not the only newer
    file. ``os.utime`` failure is a hard failure.
    """
    assert oid, "object id is empty"
    store = default_lfs_store_root(ws)
    path = store / sharded_object_rel(oid)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"cannot bitflip stored object; missing at {path}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot read stored object at {path}: {exc}"
        ) from exc
    assert data, f"cannot bitflip empty stored object at {path}"
    if align_mtime_oid is not None:
        assert align_mtime_oid, "align_mtime_oid is empty"
        align_path = store / sharded_object_rel(align_mtime_oid)
        try:
            stamp_st = align_path.stat()
        except FileNotFoundError:
            raise AssertionError(
                f"cannot read align stamp; missing at {align_path}"
            ) from None
        except OSError as exc:
            raise AssertionError(
                f"cannot stat align object at {align_path}: {exc}"
            ) from exc
    else:
        align_path = None
        try:
            stamp_st = path.stat()
        except OSError as exc:
            raise AssertionError(f"cannot stat {path}: {exc}") from exc
    stamp = (stamp_st.st_atime, stamp_st.st_mtime)
    flipped = bytearray(data)
    flipped[0] ^= 0x01
    new_data = bytes(flipped)
    assert new_data != data, (
        f"bitflip of {path} produced identical bytes"
    )
    # A product may legitimately store objects read-only; the judge runs
    # unprivileged, so add owner write permission for the write-back and
    # restore the original mode afterwards.
    try:
        orig_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise AssertionError(f"cannot stat {path}: {exc}") from exc
    try:
        if not orig_mode & stat.S_IWUSR:
            os.chmod(path, orig_mode | stat.S_IWUSR)
        try:
            path.write_bytes(new_data)
        finally:
            if not orig_mode & stat.S_IWUSR:
                os.chmod(path, orig_mode)
    except OSError as exc:
        raise AssertionError(
            f"cannot write flipped object at {path}: {exc}"
        ) from exc
    try:
        os.utime(path, stamp)
    except OSError as exc:
        raise AssertionError(
            f"cannot align timestamp of flipped object at {path}: {exc}"
        ) from exc
    if align_path is not None:
        try:
            os.utime(align_path, stamp)
        except OSError as exc:
            raise AssertionError(
                f"cannot align timestamp of neighbor at {align_path}: {exc}"
            ) from exc
    return new_data


def stage_tracked_payload(ws: Workspace, relpath: str, data: bytes) -> str:
    """Write and ``git add`` *data* at *relpath* without committing.

    Filters and track pattern must already be configured. A failed add
    is not treated as a stored object. Does not rewrite
    ``commit_tracked_payload``.
    """
    ws.write(relpath, data)
    digest = sha256_hex(data)
    to_add = [relpath]
    try:
        ws.read_bytes(".gitattributes")
        to_add.append(".gitattributes")
    except FileNotFoundError:
        pass
    added = ws.git(["add", "--", *to_add])
    assert added.returncode == 0, (
        f"git add {to_add!r} failed (exit {added.returncode}): "
        f"{added.stderr_text}"
    )
    return digest


def git_add_unfiltered(ws: Workspace, relpath: str) -> RunResult:
    """Add *relpath* with LFS filters off so working-tree bytes enter the index.

    Setup only. A non-zero add is a hard failure.
    """
    assert relpath, "unfiltered add path is empty"
    result = ws.git(
        [
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.clean=cat",
            "-c",
            "filter.lfs.required=false",
            "add",
            "--",
            relpath,
        ]
    )
    assert result.returncode == 0, (
        f"unfiltered git add {relpath!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result


# ---------------------------------------------------------------------------
# F14: history migration (new names only)
# ---------------------------------------------------------------------------


def run_migrate(
    ws: Workspace,
    argv: Sequence[str] | None = None,
    *,
    via_git: bool = True,
    cwd: str | Path | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run the migrate porcelain with *argv* after the subcommand name."""
    args = ["migrate", *[str(item) for item in (argv or ())]]
    if via_git:
        return ws.invoke_via_git(args, cwd=cwd, env_updates=env_updates)
    return ws.invoke(args, cwd=cwd, env_updates=env_updates)


def blob_at(ws: Workspace, spec: str) -> bytes:
    """Return ``git cat-file -p spec``. Non-zero is not an empty blob."""
    assert spec, "blob spec is empty; cannot classify a tree blob"
    result = ws.git(["cat-file", "-p", spec])
    assert result.returncode == 0, (
        f"git cat-file -p {spec!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result.stdout


def blob_size_at(ws: Workspace, spec: str) -> int:
    """Return ``git cat-file -s spec``. Non-zero is not size 0."""
    assert spec, "blob spec is empty; cannot classify a blob size"
    result = ws.git(["cat-file", "-s", spec])
    assert result.returncode == 0, (
        f"git cat-file -s {spec!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    raw = result.stdout_text.strip()
    assert raw, (
        f"git cat-file -s {spec!r} produced no size: {result.stdout!r}"
    )
    try:
        return int(raw)
    except ValueError as exc:
        raise AssertionError(
            f"git cat-file -s {spec!r} is not an integer: {raw!r}"
        ) from exc


def attrs_blob_at(ws: Workspace, commit: str) -> bytes:
    """Return ``commit:.gitattributes``. Missing is a hard failure."""
    assert commit, "commit is empty; cannot read attributes blob"
    return blob_at(ws, f"{commit}:.gitattributes")


def require_tree_blob_bytes(
    ws: Workspace, commit: str, path: str, data: bytes
) -> bytes:
    """Require *path* at *commit* equals *data* as an ordinary blob."""
    assert commit, "commit is empty"
    assert path, "tree path is empty"
    observed = blob_at(ws, f"{commit}:{path}")
    assert observed == data, (
        f"{commit}:{path} is not the expected blob bytes "
        f"(got {len(observed)} bytes, expected {len(data)})"
    )
    return observed


def require_tree_pointer(
    ws: Workspace,
    commit: str,
    path: str,
    digest: str,
    size: int,
) -> bytes:
    """Require *path* at *commit* is a pointer for *digest*/*size*."""
    assert commit, "commit is empty"
    assert path, "tree path is empty"
    observed = blob_at(ws, f"{commit}:{path}")
    assert pointer_matches_digest_and_size(
        observed, digest=digest, size=size
    ), (
        f"{commit}:{path} is not a pointer for digest {digest!r} "
        f"size={size}: bytes={observed!r}"
    )
    return observed


def _attr_payload_lines(text: str) -> list[tuple[str, list[str], str]]:
    """Yield (pattern, rest-tokens, raw-line) skipping comments and blanks."""
    lines: list[tuple[str, list[str], str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if not parts:
            continue
        lines.append((parts[0], parts[1:], stripped))
    return lines


def require_tracking_pattern_in_attrs(text: str, pattern: str) -> str:
    """Require *pattern* appears with filter enabled as ``lfs``.

    Does not pin diff/merge/-text spelling. A comment that only mentions
    the pattern is not a tracking line.
    """
    assert pattern, "tracking pattern is empty"
    assert text, (
        "attributes text is empty; no tracking line for "
        f"{pattern!r}"
    )
    saw_pattern = False
    for first, rest, _raw in _attr_payload_lines(text):
        if first != pattern:
            continue
        saw_pattern = True
        if "filter=lfs" in rest:
            return text
    if not saw_pattern:
        raise AssertionError(
            "attributes have no non-comment line whose pattern is "
            f"{pattern!r}: {text!r}"
        )
    raise AssertionError(
        "attributes name "
        f"{pattern!r} but do not enable filter as lfs: {text!r}"
    )


def require_excluded_pattern_in_attrs(text: str, pattern: str) -> str:
    """Require *pattern* has an FP-04 excluded filter form.

    Accepts Git filter negation (``-filter``), empty unset (``filter=``),
    or unspecified (``!filter``). Merely omitting ``filter=lfs`` is not
    an excluded-pattern entry.
    """
    assert pattern, "excluded pattern is empty"
    assert text, (
        "attributes text is empty; no excluded-pattern entry for "
        f"{pattern!r}"
    )
    saw_pattern = False
    for first, rest, _raw in _attr_payload_lines(text):
        if first != pattern:
            continue
        saw_pattern = True
        if "-filter" in rest or "!filter" in rest:
            return text
        for tok in rest:
            if tok == "filter=" or tok == 'filter=""' or tok == "filter=''":
                return text
    if not saw_pattern:
        raise AssertionError(
            "attributes have no non-comment line whose pattern is "
            f"{pattern!r}: {text!r}"
        )
    raise AssertionError(
        "attributes name "
        f"{pattern!r} but have no excluded-pattern filter form "
        f"(-filter, filter=, or !filter): {text!r}"
    )


def require_attrs_not_executable(ws: Workspace, commit: str) -> str:
    """Require ``.gitattributes`` at *commit* has no execute bits."""
    assert commit, "commit is empty"
    result = ws.git(["ls-tree", commit, "--", ".gitattributes"])
    assert result.returncode == 0, (
        f"git ls-tree {commit} -- .gitattributes failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    line = result.stdout_text.strip()
    assert line, (
        f"no .gitattributes tree entry at {commit}: {result.stdout!r}"
    )
    mode_s = line.split()[0]
    try:
        mode = int(mode_s, 8)
    except ValueError as exc:
        raise AssertionError(
            f"cannot parse ls-tree mode {mode_s!r} from {line!r}"
        ) from exc
    assert (mode & 0o111) == 0, (
        f".gitattributes at {commit} is executable, mode={mode_s} "
        f"line={line!r}"
    )
    return mode_s


def info_visible(result: RunResult) -> str:
    """Caller-visible info text. Non-zero is not an empty summary."""
    assert result.returncode == 0, (
        "migrate info failed "
        f"(exit {result.returncode}) argv={list(result.argv)!r}: "
        f"{result.stderr_text}"
    )
    text = caller_visible(result)
    assert text.strip(), (
        "migrate info produced no caller-visible type summary"
    )
    return text


def type_report(visible: str, ext_token: str) -> str:
    """Return the type-report fragment bound to *ext_token*.

    Missing the extension is a hard failure, never an empty report.
    """
    assert ext_token, "extension token is empty"
    assert visible.strip(), (
        "info visible text is empty; cannot classify a type report"
    )
    lines = [line for line in visible.splitlines() if ext_token in line]
    assert lines, (
        f"info did not name extension {ext_token!r}: {visible!r}"
    )
    return "\n".join(lines)


def type_report_remainder(report: str, strip: Sequence[str]) -> str:
    """Strip covariate tokens from a type report. Empty leftover is empty."""
    remainder = _strip_unrelated_tokens(report, [str(item) for item in strip if item])
    return " ".join(remainder.split())


def decimal_integers(text: str) -> list[int]:
    """Extract decimal integers from *text*.

    A report with no digits yields an empty list. That is not a parse
    failure. Non-text input is unclassified.
    """
    if not isinstance(text, str):
        raise AssertionError(
            f"decimal_integers expected text, got {type(text).__name__}"
        )
    return [int(match) for match in re.findall(r"\d+", text)]


# ---------------------------------------------------------------------------
# F15: configuration surface and repository .lfsconfig (new names only)
# ---------------------------------------------------------------------------


def require_lfsconfig_set(ws: Workspace, key: str, value: str) -> RunResult:
    """Write *key* into worktree ``.lfsconfig``. Git non-zero is not ignored."""
    assert key, "lfsconfig key is empty"
    result = ws.git_config_set(key, value, file=".lfsconfig")
    assert result.returncode == 0, (
        f"git config --file=.lfsconfig {key!r} failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result


def unlink_worktree_lfsconfig(ws: Workspace) -> None:
    """Delete the worktree ``.lfsconfig`` file. Missing is not index fallback."""
    path = ws.resolve(".lfsconfig")
    try:
        path.unlink()
    except FileNotFoundError:
        raise AssertionError(
            "cannot unlink worktree .lfsconfig; file is missing"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot unlink worktree .lfsconfig at {path}: {exc}"
        ) from exc


def documented_truthy_skip() -> str:
    """One documented truthy token for skip / progress-forcing SET."""
    return "true"


def documented_falsey() -> str:
    """One documented falsey token for boolean SET."""
    return "false"


def non_truthy_boolean_token() -> str:
    """Runtime-unique non-truthy token; cannot collide with documented truthy."""
    return f"typo-{token()}"


def env_skip_smudge(value: str) -> dict[str, str]:
    """Environment mapping that SETs skip-smudge to *value*. Not an output pin."""
    assert value, "skip-smudge environment value is empty"
    return {"GIT_ORBULK_SKIP_SMUDGE": value}


def env_skip_push(value: str) -> dict[str, str]:
    """Environment mapping that SETs skip-push to *value*. Not an output pin."""
    assert value, "skip-push environment value is empty"
    return {"GIT_ORBULK_SKIP_PUSH": value}


def env_skip_download_errors(value: str) -> dict[str, str]:
    """Environment mapping that SETs skip-download-errors to *value*."""
    assert value, "skip-download-errors environment value is empty"
    return {"GIT_ORBULK_SKIP_DOWNLOAD_ERRORS": value}


def env_force_progress(value: str) -> dict[str, str]:
    """Environment mapping that SETs progress-forcing to *value*."""
    assert value, "force-progress environment value is empty"
    return {"GIT_ORBULK_FORCE_PROGRESS": value}


def env_lockable_readonly(value: str) -> dict[str, str]:
    """Environment mapping that SETs lockable read-only to *value*."""
    assert value, "lockable-readonly environment value is empty"
    return {"GIT_ORBULK_SET_LOCKABLE_READONLY": value}


def configure_force_progress(ws: Workspace, value: str) -> None:
    """Setup: SET local progress-forcing. Does not rewrite skip helpers."""
    require_git_config_set(ws, "lfs.forceprogress", value, local=True)


def configure_lockable_readonly(ws: Workspace, value: str) -> None:
    """Setup: SET local lockable read-only. Does not assert output."""
    require_git_config_set(ws, "lfs.setlockablereadonly", value, local=True)


def configure_skip_download_errors(ws: Workspace, value: str) -> None:
    """Setup: SET local skip-download-errors. Does not rewrite the truthy helper."""
    require_git_config_set(ws, "lfs.skipdownloaderrors", value, local=True)


def in_progress_remainder(
    on: RunResult, off: RunResult, *, strip: Sequence[str]
) -> str:
    """Return the on-arm in-progress leftover after shared completion chunks.

    Both streams are read through ``caller_visible``. *strip* must include
    paths, object ids, URLs, payload substrings, absolute paths, and the
    on/off condition tokens (SET truthy/falsey text, config-key spelling,
    environment-variable name). After those covariates are removed, text
    is split on Unix newlines and carriage returns. Chunks present on both
    arms are completion/summary. The enabled arm must still have a
    non-empty remainder; that remainder must not equal the disabled arm's
    leftover. A read that cannot classify must not return empty as
    'no progress'.
    """
    vis_on = caller_visible(on)
    vis_off = caller_visible(off)
    tokens = [str(item) for item in strip if item]
    stripped_on = _strip_unrelated_tokens(vis_on, tokens)
    stripped_off = _strip_unrelated_tokens(vis_off, tokens)

    def _chunks(text: str) -> list[str]:
        parts = re.split(r"[\n\r]+", text)
        return [part.strip() for part in parts if part.strip()]

    on_chunks = _chunks(stripped_on)
    off_chunks = _chunks(stripped_off)
    shared = set(on_chunks) & set(off_chunks)
    on_remain = [chunk for chunk in on_chunks if chunk not in shared]
    off_remain = [chunk for chunk in off_chunks if chunk not in shared]
    remainder = " ".join(on_remain)
    off_text = " ".join(off_remain)
    print(
        f"in_progress on_remain={on_remain!r} off_remain={off_remain!r} "
        f"shared_n={len(shared)}"
    )
    assert remainder.strip(), (
        "no in-progress remainder on the enabled arm after stripping "
        "covariates and shared completion chunks: "
        f"on={vis_on!r} off={vis_off!r}"
    )
    assert remainder != off_text, (
        "in-progress remainder was not distinguishable from the disabled "
        f"arm after shared-chunk removal: {remainder!r} vs {off_text!r}"
    )
    return remainder


def in_progress_on_remainder_off_empty(
    on: RunResult,
    off: RunResult,
    *,
    strip: Sequence[str],
    ignore: Sequence[RunResult] = (),
) -> str:
    """Require a non-empty on-arm leftover and an empty off-arm leftover.

    Same covariate and shared-completion-chunk stripping as
    ``in_progress_remainder``. Chunks that remain on *ignore* runs after
    the same strip are also treated as non-progress (a coupled warning
    from an unrelated .lfsconfig ignore, not in-progress reporting).
    The only accepted green path is a non-empty enabled / Git-config-on
    / truthy remainder together with an empty disabled / non-truthy /
    ignored-.lfsconfig remainder. Two different unique leftovers are
    not a contrast. A read that cannot classify must not return empty
    as 'no progress'.
    """
    vis_on = caller_visible(on)
    vis_off = caller_visible(off)
    tokens = [str(item) for item in strip if item]
    stripped_on = _strip_unrelated_tokens(vis_on, tokens)
    stripped_off = _strip_unrelated_tokens(vis_off, tokens)

    def _chunks(text: str) -> list[str]:
        parts = re.split(r"[\n\r]+", text)
        return [part.strip() for part in parts if part.strip()]

    on_chunks = _chunks(stripped_on)
    off_chunks = _chunks(stripped_off)
    ignored: set[str] = set()
    for extra in ignore:
        ignored.update(
            _chunks(
                _strip_unrelated_tokens(caller_visible(extra), tokens)
            )
        )
    shared = set(on_chunks) & set(off_chunks)
    drop = shared | ignored
    on_remain = [chunk for chunk in on_chunks if chunk not in drop]
    off_remain = [chunk for chunk in off_chunks if chunk not in drop]
    remainder = " ".join(on_remain)
    off_text = " ".join(off_remain)
    print(
        f"in_progress_off_empty on_remain={on_remain!r} "
        f"off_remain={off_remain!r} shared_n={len(shared)} "
        f"ignored_n={len(ignored)}"
    )
    assert remainder.strip(), (
        "no in-progress remainder on the enabled arm after stripping "
        "covariates and shared completion chunks: "
        f"on={vis_on!r} off={vis_off!r}"
    )
    assert not off_text.strip(), (
        "disabled arm still had a leftover after stripping covariates "
        "and shared completion chunks; in-progress reporting must be "
        f"absent on that arm: {off_remain!r} on={vis_on!r} off={vis_off!r}"
    )
    return remainder


def require_env_report_names(report: str, *values: str) -> str:
    """Require each configured value appears in the environment report.

    Does not pin labels, layout, or key spelling. An empty value is
    unclassified. Missing is a hard failure, never 'not configured'.
    """
    assert report.strip(), (
        "environment report is empty; cannot observe configured values"
    )
    for value in values:
        assert value, "configured value is empty; cannot observe it in env"
        assert value in report, (
            "environment report did not name configured value "
            f"{value!r}: {report!r}"
        )
    return report


def configure_ssh_transfer_mode(ws: Workspace, mode: str) -> None:
    """Setup: SET pure SSH transfer mode. Does not rewrite force_hybrid_ssh."""
    assert mode in ("negotiate", "always", "never"), (
        f"ssh transfer mode must be negotiate, always, or never, got {mode!r}"
    )
    require_git_config_set(ws, "lfs.sshtransfer", mode, local=True)


def configure_http_timeouts(
    ws: Workspace,
    *,
    dial: int,
    tls: int,
    activity: int,
    keepalive: int,
) -> None:
    """Setup: SET dial/TLS/activity/keepalive timeouts. Does not assert output."""
    require_git_config_set(ws, "lfs.dialtimeout", str(dial), local=True)
    require_git_config_set(ws, "lfs.tlstimeout", str(tls), local=True)
    require_git_config_set(ws, "lfs.activitytimeout", str(activity), local=True)
    require_git_config_set(ws, "lfs.keepalive", str(keepalive), local=True)


def configure_custom_transfer_agent(
    ws: Workspace, name: str, path: str | Path
) -> None:
    """Setup: bind a named custom transfer agent. Does not assert output."""
    assert name, "custom transfer agent name is empty"
    require_git_config_set(
        ws, f"lfs.customtransfer.{name}.path", str(path), local=True
    )


def configure_standalone_transfer_agent(ws: Workspace, name: str) -> None:
    """Setup: SET the standalone transfer agent binding. Does not assert output."""
    assert name, "standalone transfer agent name is empty"
    require_git_config_set(ws, "lfs.standalonetransferagent", name, local=True)


def configure_default_remote(ws: Workspace, name: str) -> None:
    """Setup: SET the LFS default remote name. Does not assert output."""
    assert name, "default remote name is empty"
    require_git_config_set(ws, "remote.lfsdefault", name, local=True)


def configure_prune_verify_defaults(
    ws: Workspace, *, offset_days: int, verify_remote: str
) -> None:
    """Setup: SET prune offset and verify-remote default. Does not assert output."""
    require_git_config_set(
        ws, "lfs.pruneoffsetdays", str(offset_days), local=True
    )
    require_git_config_set(
        ws, "lfs.pruneverifyremotealways", verify_remote, local=True
    )


# ---------------------------------------------------------------------------
# F16: custom transfers, standalone file URLs, clean/smudge extensions
# ---------------------------------------------------------------------------


@dataclass
class AgentProbe:
    """Fixture process that speaks line-delimited JSON and copies via paths."""

    path: Path
    marker: Path
    control_log: Path
    writes_dir: Path
    seed_dir: Path
    handoff_dir: Path


class NamedTransferBatchServer:
    """Loopback batch+basic fixture that selects *select* only when advertised."""

    def __init__(
        self,
        *,
        url: str,
        records: list[RecordedHttpExchange],
        header_name: str,
        header_value: str,
        action_paths: dict[str, str],
        payloads: dict[str, bytes],
        select: str,
    ) -> None:
        self.url = url
        self.records = records
        self.header_name = header_name
        self.header_value = header_value
        self.action_paths = action_paths
        self.payloads = payloads
        self.select = select

    def action_path(self, oid: str | None = None) -> str:
        if oid is None:
            assert len(self.action_paths) == 1, (
                "action_path() without oid requires exactly one registered "
                f"object, got {list(self.action_paths)!r}"
            )
            return next(iter(self.action_paths.values()))
        assert oid in self.action_paths, (
            f"no action path for oid {oid!r}; known={list(self.action_paths)!r}"
        )
        return self.action_paths[oid]

    def action_href(self, oid: str | None = None) -> str:
        return self.url.rstrip("/") + self.action_path(oid)


def install_json_path_agent(ws: Workspace) -> AgentProbe:
    """Write a test-owned JSON path agent. Does not assert product output."""
    tag = token()
    probe_rel = f"agent_probe_{tag}"
    marker = ws.resolve(f"{probe_rel}/launched")
    control_log = ws.resolve(f"{probe_rel}/control.log")
    writes_dir = ws.resolve(f"{probe_rel}/writes")
    seed_dir = ws.resolve(f"{probe_rel}/seed")
    handoff_dir = ws.resolve(f"{probe_rel}/handoff")
    writes_dir.mkdir(parents=True, exist_ok=True)
    seed_dir.mkdir(parents=True, exist_ok=True)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"MARKER = {str(marker)!r}\n"
        f"CONTROL = {str(control_log)!r}\n"
        f"WRITES = {str(writes_dir)!r}\n"
        f"SEED = {str(seed_dir)!r}\n"
        f"HANDOFF = {str(handoff_dir)!r}\n"
        "Path(MARKER).write_text('launched\\n', encoding='utf-8')\n"
        "for d in (WRITES, SEED, HANDOFF):\n"
        "    os.makedirs(d, exist_ok=True)\n"
        "\n"
        "def _log(line):\n"
        "    if isinstance(line, str):\n"
        "        blob = line.encode('utf-8')\n"
        "    else:\n"
        "        blob = line\n"
        "    if blob and not blob.endswith(b'\\n'):\n"
        "        blob += b'\\n'\n"
        "    with open(CONTROL, 'ab') as handle:\n"
        "        handle.write(blob)\n"
        "\n"
        "def _reply(obj):\n"
        "    text = json.dumps(obj) + '\\n'\n"
        "    _log(text)\n"
        "    sys.stdout.write(text)\n"
        "    sys.stdout.flush()\n"
        "\n"
        "for raw in sys.stdin:\n"
        "    _log(raw)\n"
        "    try:\n"
        "        msg = json.loads(raw)\n"
        "    except json.JSONDecodeError:\n"
        "        sys.exit(2)\n"
        "    if not isinstance(msg, dict):\n"
        "        sys.exit(2)\n"
        "    event = str(msg.get('event') or '')\n"
        "    if event == 'init':\n"
        "        _reply({})\n"
        "        continue\n"
        "    if event == 'terminate':\n"
        "        break\n"
        "    oid = str(msg.get('oid') or '')\n"
        "    if event == 'upload':\n"
        "        src = Path(str(msg.get('path') or ''))\n"
        "        data = src.read_bytes()\n"
        "        (Path(WRITES) / ('up_' + oid)).write_bytes(data)\n"
        "        (Path(SEED) / oid).write_bytes(data)\n"
        "        _reply({\n"
        "            'event': 'progress',\n"
        "            'oid': oid,\n"
        "            'bytesSoFar': len(data),\n"
        "            'bytesSinceLast': len(data),\n"
        "        })\n"
        "        _reply({'event': 'complete', 'oid': oid})\n"
        "        continue\n"
        "    if event == 'download':\n"
        "        src = Path(SEED) / oid\n"
        "        try:\n"
        "            data = src.read_bytes()\n"
        "        except FileNotFoundError:\n"
        "            _reply({\n"
        "                'event': 'complete',\n"
        "                'oid': oid,\n"
        "                'error': {'code': 2, 'message': 'missing'},\n"
        "            })\n"
        "            continue\n"
        "        (Path(WRITES) / ('dn_' + oid)).write_bytes(data)\n"
        "        hand = Path(HANDOFF) / oid\n"
        "        hand.write_bytes(data)\n"
        "        _reply({\n"
        "            'event': 'progress',\n"
        "            'oid': oid,\n"
        "            'bytesSoFar': len(data),\n"
        "            'bytesSinceLast': len(data),\n"
        "        })\n"
        "        _reply({'event': 'complete', 'oid': oid, 'path': str(hand)})\n"
        "        continue\n"
    )
    path = ws.write(f"{probe_rel}/agent.py", script)
    path.chmod(0o755)
    return AgentProbe(
        path=path,
        marker=marker,
        control_log=control_log,
        writes_dir=writes_dir,
        seed_dir=seed_dir,
        handoff_dir=handoff_dir,
    )


def unlaunchable_process_path(ws: Workspace) -> Path:
    """Return a workspace path that does not exist and is not executable."""
    path = ws.resolve(f"missing_agent_{token()}")
    if path.exists():
        raise AssertionError(
            f"unlaunchable path unexpectedly exists: {path}"
        )
    return path


def seed_agent_payload(probe: AgentProbe, data: bytes) -> str:
    """Place *data* in the agent's download seed store keyed by independent oid."""
    oid = sha256_hex(data)
    try:
        probe.seed_dir.mkdir(parents=True, exist_ok=True)
        dest = probe.seed_dir / oid
        dest.write_bytes(data)
    except OSError as exc:
        raise AssertionError(
            f"cannot seed agent payload at {probe.seed_dir}: {exc}"
        ) from exc
    return oid


def agent_was_launched(probe: AgentProbe) -> None:
    """Require the agent process wrote its launch marker. Read failure is not absence."""
    try:
        data = probe.marker.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"agent was not launched; marker missing at {probe.marker}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot read agent launch marker at {probe.marker}: {exc}"
        ) from exc
    assert data, f"agent launch marker at {probe.marker} is empty"


def agent_wrote_payload(probe: AgentProbe, payload: bytes) -> Path:
    """Require a file in the agent writes directory equals *payload*."""
    writes = probe.writes_dir
    try:
        names = os.listdir(writes)
    except FileNotFoundError:
        raise AssertionError(
            f"agent writes directory is missing at {writes}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot list agent writes directory {writes}: {exc}"
        ) from exc
    matched: list[Path] = []
    for name in names:
        path = writes / name
        try:
            is_file = path.is_file()
        except OSError as exc:
            raise AssertionError(f"cannot stat {path}: {exc}") from exc
        if not is_file:
            continue
        try:
            body = path.read_bytes()
        except OSError as exc:
            raise AssertionError(f"cannot read {path}: {exc}") from exc
        if body == payload:
            matched.append(path)
    assert matched, (
        "agent did not write the payload bytes to a path it understands "
        f"at {writes} (entries={names!r})"
    )
    return matched[0]


def agent_control_has_json_without_payload(
    probe: AgentProbe, payload: bytes
) -> bytes:
    """Require a parseable JSON object on the control stream and no payload bytes."""
    try:
        raw = probe.control_log.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"agent control stream is missing at {probe.control_log}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot read agent control stream {probe.control_log}: {exc}"
        ) from exc
    assert raw, (
        f"agent control stream is empty at {probe.control_log}; "
        "not a JSON control protocol"
    )
    assert payload not in raw, (
        "object payload bytes appeared on the agent control stream"
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"agent control stream is not UTF-8: {exc}"
        ) from exc
    found = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found = True
            break
    assert found, (
        "agent control stream contained no parseable JSON object: "
        f"{raw!r}"
    )
    return raw


def assert_agent_was_launched(probe: AgentProbe) -> None:
    """Require the agent process wrote its launch marker.

    Same contract as ``agent_was_launched``. The name is the verdict
    the suite-bailout audit can see: a selected custom agent that never
    starts is not an invocation.
    """
    agent_was_launched(probe)


def assert_agent_wrote_payload(probe: AgentProbe, payload: bytes) -> Path:
    """Require a file in the agent writes directory equals *payload*.

    Same contract as ``agent_wrote_payload``. The name is the verdict
    the suite-bailout audit can see: a selected agent that never moves
    object bytes onto a path it understands has not transferred.
    """
    return agent_wrote_payload(probe, payload)


def assert_agent_control_has_json_without_payload(
    probe: AgentProbe, payload: bytes
) -> bytes:
    """Require a parseable JSON object on the control stream and no payload.

    Same contract as ``agent_control_has_json_without_payload``. The name
    is the verdict the suite-bailout audit can see: a control stream
    that carries object bytes, or that is not JSON, is not the custom
    transfer protocol.
    """
    return agent_control_has_json_without_payload(probe, payload)


@contextmanager
def named_transfer_batch_server(
    select: str,
    payloads: Sequence[bytes] | None = None,
) -> Iterator[NamedTransferBatchServer]:
    """Loopback batch server: select *select* only when that POST advertised it.

    JSON that cannot be parsed or a missing designated media type is
    400/406, never treated as an omitted custom advertisement.
    """
    assert select, "named_transfer_batch_server select name is empty"
    payload_list = list(payloads or ())
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()
    basic = contract_basic_adapter_name()

    def _ensure_action(oid: str) -> str:
        if oid not in action_paths:
            path = f"/obj_{token()}"
            action_paths[oid] = path
            path_to_oid[path] = oid
        return action_paths[oid]

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = _batch_headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            if path in path_to_oid and self.command == "PUT":
                self._serve_put(path, body)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            try:
                transfers = _parse_transfers_field(parsed)
            except AssertionError:
                _send_bytes(self, 400, b"")
                return
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            chosen = basic
            if isinstance(transfers, list) and select in transfers:
                chosen = select
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                href = "http://placeholder" + _ensure_action(oid)
                action = {
                    "href": href,
                    "header": {hdr_name: hdr_value},
                }
                actions: dict[str, object] = {}
                if operation == "download":
                    actions["download"] = action
                else:
                    actions["upload"] = action
                reply_objects.append(
                    {
                        "oid": oid,
                        "size": size,
                        "authenticated": True,
                        "actions": actions,
                    }
                )
            origin = _origin_for_handler(self)
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {"transfer": chosen, "objects": reply_objects}
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            data = by_oid.get(oid)
            if data is None:
                _send_bytes(self, 404, b"")
                return
            _send_bytes(
                self,
                200,
                data,
                content_type="application/octet-stream",
            )

        def _serve_put(self, path: str, body: bytes) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            expected = by_oid.get(oid)
            if expected is not None and body != expected:
                _send_bytes(self, 400, b"")
                return
            if expected is None:
                by_oid[oid] = body
            _send_bytes(self, 200, b"")

        def do_GET(self) -> None:
            self._handle()

        def do_PUT(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield NamedTransferBatchServer(
            url=svc.url,
            records=records,
            header_name=hdr_name,
            header_value=hdr_value,
            action_paths=action_paths,
            payloads=by_oid,
            select=select,
        )


def require_adapter_name_advertised(
    parsed: ParsedBatchRequest, name: str
) -> list[str]:
    """Require the advertised transfer list is a list containing *name*.

    An omitted list is not an advertisement of *name*. Unparseable JSON
    is already a hard failure in ``require_batch_post``.
    """
    assert name, "adapter name is empty"
    names = advertised_adapter_names(parsed)
    assert names is not TRANSFERS_LIST_OMITTED, (
        f"advertised transfer list was omitted; {name!r} was not advertised"
    )
    assert isinstance(names, list), (
        f"advertised transfer list is not a list: {names!r}"
    )
    assert name in names, (
        f"advertised transfer list does not include {name!r}: {names!r}"
    )
    return names


def require_no_objects_batch_post(
    records: list[RecordedHttpExchange] | None,
) -> None:
    """Require that no recorded request POSTed the objects-batch path."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify absence of a batch POST"
    )
    hits = [
        rec
        for rec in records
        if rec.method == "POST" and _is_objects_batch_path(rec.path)
    ]
    assert not hits, (
        "unexpected objects-batch POST: "
        f"{[(r.method, r.path) for r in hits]!r}"
    )


def require_no_get_of_object_action(
    records: list[RecordedHttpExchange] | None, oid_or_href: str
) -> None:
    """Require no GET of the download action href/path *oid_or_href*."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify absence of a GET"
    )
    assert oid_or_href, "action href/path is empty"
    want = _request_path(oid_or_href)
    gets = [
        rec
        for rec in records
        if rec.method == "GET" and _request_path(rec.path) == want
    ]
    assert not gets, (
        f"unexpected GET of action href {want!r}: "
        f"{[(r.method, r.path) for r in gets]!r}"
    )


def assert_adapter_name_advertised(
    parsed: ParsedBatchRequest, name: str
) -> list[str]:
    """Require the advertised transfer list is a list containing *name*.

    Same contract as ``require_adapter_name_advertised``. The name is
    the verdict the suite-bailout audit can see: an omitted list, or a
    list that does not include *name*, is not an advertisement of that
    custom agent.
    """
    return require_adapter_name_advertised(parsed, name)


def assert_no_objects_batch_post(
    records: list[RecordedHttpExchange] | None,
) -> None:
    """Require that no recorded request POSTed the objects-batch path.

    Same contract as ``require_no_objects_batch_post``. The name is the
    verdict the suite-bailout audit can see: a standalone agent that
    still POSTs objects-batch has not skipped the batch API.
    """
    require_no_objects_batch_post(records)


def assert_no_get_of_object_action(
    records: list[RecordedHttpExchange] | None, oid_or_href: str
) -> None:
    """Require no GET of the download action href/path *oid_or_href*.

    Same contract as ``require_no_get_of_object_action``. The name is
    the verdict the suite-bailout audit can see: a selected custom
    download that still GETs the action href has not moved bytes via
    the agent path.
    """
    require_no_get_of_object_action(records, oid_or_href)


def register_transform_extension(
    ws: Workspace,
    *,
    name: str,
    priority: int,
    clean_cmd: str,
    smudge_cmd: str,
) -> None:
    """SET one extension's clean/smudge commands and priority number."""
    assert name, "extension name is empty"
    assert clean_cmd, "extension clean command is empty"
    assert smudge_cmd, "extension smudge command is empty"
    require_git_config_set(
        ws, f"lfs.extension.{name}.clean", clean_cmd, local=True
    )
    require_git_config_set(
        ws, f"lfs.extension.{name}.smudge", smudge_cmd, local=True
    )
    require_git_config_set(
        ws, f"lfs.extension.{name}.priority", str(priority), local=True
    )


def append_token_transform_scripts(
    ws: Workspace, append_token: str
) -> tuple[str, str]:
    """Return mutually inverse clean/smudge commands that append/strip *append_token*."""
    assert append_token, "append token is empty"
    suffix = append_token.encode("utf-8")
    ident = f"{sha256_hex(suffix)[:8]}_{token()}"
    clean_script = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"TOKEN = {suffix!r}\n"
        "data = sys.stdin.buffer.read()\n"
        "Path(sys.argv[0] + '.stdin').write_bytes(data)\n"
        "sys.stdout.buffer.write(data + TOKEN)\n"
    )
    smudge_script = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"TOKEN = {suffix!r}\n"
        "data = sys.stdin.buffer.read()\n"
        "Path(sys.argv[0] + '.stdin').write_bytes(data)\n"
        "if data.endswith(TOKEN):\n"
        "    data = data[: -len(TOKEN)]\n"
        "sys.stdout.buffer.write(data)\n"
    )
    clean_path = ws.write(f"ext_clean_{ident}.py", clean_script)
    smudge_path = ws.write(f"ext_smudge_{ident}.py", smudge_script)
    clean_path.chmod(0o755)
    smudge_path.chmod(0o755)
    return str(clean_path), str(smudge_path)


def failing_extension_command(ws: Workspace) -> str:
    """Return a command path that exits 1. Fixture only."""
    path = ws.write(
        f"ext_fail_{token()}.py",
        "#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n",
    )
    path.chmod(0o755)
    return str(path)


def extension_command_stdin(command: str) -> bytes:
    """Read stdin captured by an append-token transform script. Missing is not empty."""
    assert command, "extension command is empty"
    script = command.split()[0]
    path = Path(script + ".stdin")
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"extension stdin capture is missing at {path}"
        ) from None
    except OSError as exc:
        raise AssertionError(
            f"cannot read extension stdin capture at {path}: {exc}"
        ) from exc


def priority_pair_numeric_not_lexicographic() -> tuple[int, int]:
    """Return (lo, hi) with lo < hi numerically but str(lo) > str(hi)."""
    n = int(token(2), 16)
    lo = 2 + (n % 8)
    m = int(token(2), 16)
    hi = 10 + (m % 10)
    assert lo > 0 and hi > 0, f"priorities must be positive, got {lo}, {hi}"
    assert lo < hi, f"numeric order failed: {lo} < {hi}"
    assert str(lo) > str(hi), (
        f"decimal literals are not reverse-lexicographic: "
        f"{lo!r} vs {hi!r}"
    )
    return lo, hi


def pointer_non_core_pairs(
    document: bytes,
) -> list[tuple[str, str]]:
    """Parse kv pairs and drop version/oid/size. Non-kv is a hard failure."""
    pairs = parse_pointer_kv(document)
    return [
        (key, value)
        for key, value in pairs
        if key not in ("version", "oid", "size")
    ]


def require_ext_listing_names(result: RunResult, *names: str) -> str:
    """Require a successful ext listing that names each registration."""
    require_success(result)
    text = listing_visible(result)
    assert text.strip(), (
        "ext produced no caller-visible listing of registered extensions"
    )
    for name in names:
        assert name, "extension name is empty"
        assert name in text, (
            f"ext listing did not name registered extension {name!r}: "
            f"{text!r}"
        )
    return text


def file_remote_url(path: Path) -> str:
    """Return a file:// URL for *path*. Does not assert product output."""
    resolved = Path(path).resolve()
    assert resolved.is_absolute(), f"file remote path is not absolute: {path}"
    return resolved.as_uri()


# ---------------------------------------------------------------------------
# F17: pure SSH transfer (git-orbulk-transfer pkt-line peer)
# ---------------------------------------------------------------------------


@dataclass
class SshTransferProbe:
    """Fake GIT_SSH peer that speaks git-orbulk-transfer and logs invocations."""

    path: Path
    argv_log: Path
    session_log: Path
    store_dir: Path
    seed_dir: Path
    sent_dir: Path


_SSH_TRANSFER_PEER_SCRIPT = r'''#!/usr/bin/env python3
import fcntl
import hashlib
import json
import os
import sys

MODE = __MODE__
ARGV_LOG = __ARGV_LOG__
SESSION_LOG = __SESSION_LOG__
STORE_DIR = __STORE_DIR__
SEED_DIR = __SEED_DIR__
SENT_DIR = __SENT_DIR__
AUTH = __AUTH__
PID = os.getpid()

inp = sys.stdin.buffer
out = sys.stdout.buffer


def _lock_write(path, line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(line)
        if not line.endswith("\n"):
            handle.write("\n")
        handle.flush()


def log_argv(argv):
    _lock_write(ARGV_LOG, json.dumps(list(argv)))


def log_event(event, **fields):
    rec = {"event": event, "pid": PID}
    rec.update(fields)
    _lock_write(SESSION_LOG, json.dumps(rec))


def write_raw(payload):
    header = f"{len(payload) + 4:04x}".encode("ascii")
    out.write(header + payload)
    out.flush()


def write_text(text):
    write_raw((text + "\n").encode("utf-8"))


def write_flush():
    out.write(b"0000")
    out.flush()


def write_delim():
    out.write(b"0001")
    out.flush()


def read_packet():
    header = inp.read(4)
    if not header:
        return None, None
    if len(header) < 4:
        sys.exit(1)
    if header == b"0000":
        return 0, b""
    if header == b"0001":
        return 1, b""
    try:
        length = int(header, 16)
    except ValueError:
        sys.exit(1)
    if length < 4:
        sys.exit(1)
    payload = inp.read(length - 4)
    if len(payload) != length - 4:
        sys.exit(1)
    return length, payload


def packet_text(payload):
    text = payload.decode("utf-8", errors="replace")
    if text.endswith("\n"):
        text = text[:-1]
    return text


def read_request():
    parts = []
    body = []
    saw_delim = False
    while True:
        pkt_len, payload = read_packet()
        if pkt_len is None:
            return None, None, None, None
        if pkt_len == 0:
            break
        if pkt_len == 1:
            saw_delim = True
            continue
        if saw_delim:
            body.append(payload)
        else:
            parts.append(packet_text(payload))
    if not parts:
        return "", [], saw_delim, body
    return parts[0], parts[1:], saw_delim, body


def send_status(code, args=None, lines=None, data=None):
    write_text("status " + str(code))
    for item in args or []:
        write_text(item)
    if data is not None:
        write_delim()
        view = memoryview(data)
        offset = 0
        while offset < len(data):
            chunk = bytes(view[offset : offset + 32768])
            write_raw(chunk)
            offset += 32768
        write_flush()
        return
    if lines is not None:
        write_delim()
        for line in lines:
            write_text(line)
        write_flush()
        return
    write_flush()


def send_error(code=500):
    send_status(code, lines=["transfer failed"])


def oid_from_command(command):
    bits = command.split()
    if len(bits) >= 2:
        return bits[1]
    return ""


def load_object(oid):
    for directory in (SEED_DIR, STORE_DIR):
        path = os.path.join(directory, oid)
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except FileNotFoundError:
            continue
        except OSError:
            sys.exit(1)
    return None


def digest_of(data):
    return hashlib.sha256(data).hexdigest()


def serve_transfer(operation):
    write_text("version=1")
    write_flush()
    stored_this_conn = False
    while True:
        command, args, saw_delim, body = read_request()
        if command is None:
            return
        if not command:
            continue
        if command.startswith("version "):
            log_event("version_selected", version=1)
            send_status(200)
            continue
        if command == "quit" or command.startswith("quit "):
            send_status(200)
            return
        if command == "batch" or command.startswith("batch "):
            lines = []
            for raw in body:
                line = packet_text(raw).strip()
                if not line:
                    continue
                bits = line.split()
                if len(bits) < 2:
                    continue
                oid, size = bits[0], bits[1]
                action = "download" if operation == "download" else "upload"
                lines.append(f"{oid} {size} {action}")
            send_status(200, args=["hash-algo=sha256"], lines=lines)
            continue
        if command.startswith("get-object"):
            oid = oid_from_command(command)
            if MODE == "download_error":
                send_error()
                continue
            data = load_object(oid)
            if data is None:
                send_error(404)
                continue
            sent_path = os.path.join(SENT_DIR, oid)
            try:
                with open(sent_path, "wb") as handle:
                    handle.write(data)
            except OSError:
                sys.exit(1)
            log_event(
                "channel_sent",
                digest=digest_of(data),
                size=len(data),
                oid=oid,
            )
            send_status(
                200,
                args=[f"size={len(data)}"],
                data=data,
            )
            continue
        if command.startswith("put-object"):
            oid = oid_from_command(command)
            data = b"".join(body)
            if MODE == "put_error":
                log_event("put_error", oid=oid, size=len(data))
                send_error()
                continue
            dest = os.path.join(STORE_DIR, oid)
            try:
                with open(dest, "wb") as handle:
                    handle.write(data)
            except OSError:
                sys.exit(1)
            stored_this_conn = True
            log_event(
                "peer_stored",
                digest=digest_of(data),
                size=len(data),
                oid=oid,
            )
            send_status(200)
            continue
        if stored_this_conn:
            log_event("post_put_roundtrip", command=command.split()[0])
            if MODE == "verify_error":
                send_error()
                continue
            send_status(200)
            continue
        send_status(200)


def handle_control_master(argv):
    master = None
    path = None
    for item in argv:
        if item.startswith("-oControlMaster="):
            master = item.split("=", 1)[1]
        elif item.startswith("-oControlPath="):
            path = item.split("=", 1)[1]
    if master == "yes" and path:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            os.close(fd)
        except FileExistsError:
            pass
        except OSError:
            pass


def classify_remote(argv):
    joined = " ".join(argv)
    if "git-orbulk-authenticate" in joined:
        return "authenticate"
    if "git-orbulk-transfer" in joined:
        operation = "download"
        if " upload" in (" " + joined + " ") or joined.endswith(" upload"):
            operation = "upload"
        for item in argv:
            bits = item.split()
            if len(bits) >= 3 and bits[0] == "git-orbulk-transfer":
                if bits[2] in ("download", "upload"):
                    operation = bits[2]
        return "transfer", operation
    return "other"


def main():
    argv = sys.argv[1:]
    log_argv(argv)
    handle_control_master(argv)
    kind = classify_remote(argv)
    if kind == "authenticate":
        if AUTH is None:
            sys.exit(1)
        blob = AUTH if isinstance(AUTH, bytes) else AUTH.encode("utf-8")
        if blob and not blob.endswith(b"\n"):
            blob += b"\n"
        out.write(blob)
        out.flush()
        sys.exit(0)
    if isinstance(kind, tuple) and kind[0] == "transfer":
        if MODE == "no_session":
            sys.exit(1)
        serve_transfer(kind[1])
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
'''


def install_ssh_transfer_peer(
    ws: Workspace,
    *,
    mode: str,
    authenticate_json: str | None = None,
) -> SshTransferProbe:
    """Write a GIT_SSH script that speaks git-orbulk-transfer pkt-line.

    *mode* is ``serve``, ``no_session``, ``download_error``, ``put_error``,
    or ``verify_error``. Every invocation appends argv as a JSON line
    before speaking. ``GIT_SSH_COMMAND`` is left for ``ssh_env_updates``.
    """
    allowed = (
        "serve",
        "no_session",
        "download_error",
        "put_error",
        "verify_error",
    )
    assert mode in allowed, f"unknown ssh transfer peer mode: {mode!r}"
    tag = token()
    probe_rel = f"ssh_xfer_{tag}"
    argv_log = ws.resolve(f"{probe_rel}/argv.log")
    session_log = ws.resolve(f"{probe_rel}/session.log")
    store_dir = ws.resolve(f"{probe_rel}/store")
    seed_dir = ws.resolve(f"{probe_rel}/seed")
    sent_dir = ws.resolve(f"{probe_rel}/sent")
    store_dir.mkdir(parents=True, exist_ok=True)
    seed_dir.mkdir(parents=True, exist_ok=True)
    sent_dir.mkdir(parents=True, exist_ok=True)
    argv_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        argv_log.write_text("", encoding="utf-8")
        session_log.write_text("", encoding="utf-8")
    except OSError as exc:
        raise AssertionError(
            f"cannot create ssh transfer probe logs under {probe_rel}: {exc}"
        ) from exc
    auth_literal = (
        "None" if authenticate_json is None else json.dumps(authenticate_json)
    )
    script = (
        _SSH_TRANSFER_PEER_SCRIPT.replace("__MODE__", json.dumps(mode))
        .replace("__ARGV_LOG__", json.dumps(str(argv_log)))
        .replace("__SESSION_LOG__", json.dumps(str(session_log)))
        .replace("__STORE_DIR__", json.dumps(str(store_dir)))
        .replace("__SEED_DIR__", json.dumps(str(seed_dir)))
        .replace("__SENT_DIR__", json.dumps(str(sent_dir)))
        .replace("__AUTH__", auth_literal)
    )
    path = ws.write(f"{probe_rel}/ssh.py", script)
    path.chmod(0o755)
    return SshTransferProbe(
        path=path,
        argv_log=argv_log,
        session_log=session_log,
        store_dir=store_dir,
        seed_dir=seed_dir,
        sent_dir=sent_dir,
    )


def ssh_env_updates(probe: SshTransferProbe) -> dict[str, str | None]:
    """``GIT_SSH`` points at the probe script; ``GIT_SSH_COMMAND`` is unset."""
    return {
        "GIT_SSH": str(probe.path),
        "GIT_SSH_COMMAND": None,
    }


def ssh_style_remote() -> tuple[str, str]:
    """Runtime-generated ``git@host:path`` plus the path fragment."""
    host = f"{token()}.ssh.example.test"
    repo_path = f"{token()}/repo.git"
    return f"git@{host}:{repo_path}", repo_path


def _read_ssh_argv_log(argv_log: str | Path) -> str:
    path = Path(argv_log)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AssertionError(
            f"SSH argv log is missing at {path}"
        ) from None
    except OSError as extra:
        raise AssertionError(
            f"cannot read SSH argv log {path}: {extra}"
        ) from extra
    return text


def _argv_line_names(line: str, token_name: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    try:
        argv = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"SSH argv log line is not JSON: {line!r} ({exc})"
        ) from exc
    blob = " ".join(str(item) for item in argv)
    return token_name in blob


def require_transfer_invocation(
    argv_log: str | Path,
    *,
    repo_path_fragment: str,
    operation: str,
) -> str:
    """Require one GIT_SSH invocation names git-orbulk-transfer, path, operation.

    Missing or unreadable log, or a non-JSON line, is a hard failure.
    An empty log is classified as not invoked.
    """
    assert operation in ("download", "upload"), (
        f"transfer operation must be download or upload, got {operation!r}"
    )
    assert repo_path_fragment, "repo path fragment is empty"
    text = _read_ssh_argv_log(argv_log)
    assert text.strip(), (
        "SSH argv log is empty; git-orbulk-transfer was not invoked"
    )
    matched = False
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            argv = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"SSH argv log line is not JSON: {line!r} ({exc})"
            ) from exc
        blob = " ".join(str(item) for item in argv)
        if "git-orbulk-transfer" not in blob:
            continue
        if repo_path_fragment not in blob:
            continue
        if operation not in blob:
            continue
        matched = True
        break
    assert matched, (
        "no git-orbulk-transfer invocation named the repository path "
        f"fragment {repo_path_fragment!r} and operation {operation!r}: "
        f"{text!r}"
    )
    return text


def require_no_transfer_invocation(argv_log: str | Path) -> str:
    """Require a readable argv log with no git-orbulk-transfer line.

    Missing or unreadable log is a hard failure. A present log with no
    git-orbulk-transfer name is classified absence.
    """
    text = _read_ssh_argv_log(argv_log)
    for line in text.splitlines():
        if _argv_line_names(line, "git-orbulk-transfer"):
            raise AssertionError(
                "git-orbulk-transfer was invoked; argv log: "
                f"{text!r}"
            )
    return text


def require_no_authenticate_invocation(argv_log: str | Path) -> str:
    """Require a readable argv log with no git-orbulk-authenticate line.

    Missing or unreadable log is a hard failure. A present log with no
    git-orbulk-authenticate name is classified absence.
    """
    text = _read_ssh_argv_log(argv_log)
    for line in text.splitlines():
        if _argv_line_names(line, "git-orbulk-authenticate"):
            raise AssertionError(
                "git-orbulk-authenticate was invoked; argv log: "
                f"{text!r}"
            )
    return text


def _read_session_events(probe: SshTransferProbe) -> list[dict[str, object]]:
    path = probe.session_log
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AssertionError(
            f"ssh transfer session log is missing at {path}"
        ) from None
    except OSError as extra:
        raise AssertionError(
            f"cannot read ssh transfer session log {path}: {extra}"
        ) from extra
    events: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"session log line is not JSON: {line!r} ({exc})"
            ) from exc
        if not isinstance(obj, dict) or "event" not in obj:
            raise AssertionError(
                f"session log line is not an event object: {obj!r}"
            )
        events.append(obj)
    return events


def require_version_1_selected(probe: SshTransferProbe) -> list[dict[str, object]]:
    """Require the session log shows the client selected protocol version 1.

    Missing or unparseable log is a hard failure, never a false return.
    """
    events = _read_session_events(probe)
    selected = [
        item for item in events if item.get("event") == "version_selected"
    ]
    assert selected, (
        "session log does not show protocol version 1 was selected: "
        f"{events!r}"
    )
    return events


def require_ssh_peer_stored(probe: SshTransferProbe, payload: bytes) -> Path:
    """Require the peer store directory holds a file equal to *payload*.

    Missing directory or unreadable entries are hard failures, never absence.
    """
    store = probe.store_dir
    try:
        names = os.listdir(store)
    except FileNotFoundError:
        raise AssertionError(
            f"ssh peer store directory is missing at {store}"
        ) from None
    except OSError as extra:
        raise AssertionError(
            f"cannot list ssh peer store {store}: {extra}"
        ) from extra
    matched: list[Path] = []
    for name in names:
        path = store / name
        try:
            is_file = path.is_file()
        except OSError as extra:
            raise AssertionError(f"cannot stat {path}: {extra}") from extra
        if not is_file:
            continue
        try:
            body = path.read_bytes()
        except OSError as extra:
            raise AssertionError(f"cannot read {path}: {extra}") from extra
        if body == payload:
            matched.append(path)
    assert matched, (
        "ssh peer store has no file equal to the payload "
        f"at {store} (entries={names!r})"
    )
    return matched[0]


def require_ssh_channel_delivered(
    probe: SshTransferProbe, payload: bytes
) -> dict[str, object]:
    """Require the fixture sent *payload* on the SSH channel after version 1.

    Classification is order plus payload equality, not a command token.
    Missing or unparseable log is a hard failure.
    """
    events = require_version_1_selected(probe)
    digest = sha256_hex(payload)
    delivered: list[dict[str, object]] = []
    by_pid: dict[object, bool] = {}
    for item in events:
        pid = item.get("pid")
        if item.get("event") == "version_selected":
            by_pid[pid] = True
            continue
        if item.get("event") != "channel_sent":
            continue
        if not by_pid.get(pid):
            continue
        if item.get("digest") != digest:
            continue
        delivered.append(item)
    assert delivered, (
        "session log has no channel delivery of this payload after "
        f"version 1 was selected: digest={digest!r} events={events!r}"
    )
    rec = delivered[0]
    oid = str(rec.get("oid") or digest)
    sent_path = probe.sent_dir / oid
    try:
        body = sent_path.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"channel-sent bytes are missing at {sent_path}"
        ) from None
    except OSError as extra:
        raise AssertionError(
            f"cannot read channel-sent bytes at {sent_path}: {extra}"
        ) from extra
    assert body == payload, (
        "channel-sent file is not the payload bytes "
        f"(got {len(body)} expected {len(payload)}) at {sent_path}"
    )
    return rec


def require_post_put_roundtrip(probe: SshTransferProbe) -> dict[str, object]:
    """Require a same-channel command after object bytes were stored.

    Order only: a peer_stored event, then a later post_put_roundtrip on
    that connection. Missing or unparseable log is a hard failure.
    """
    events = _read_session_events(probe)
    stored_pids: set[object] = set()
    found: list[dict[str, object]] = []
    for item in events:
        pid = item.get("pid")
        if item.get("event") == "peer_stored":
            stored_pids.add(pid)
            continue
        if item.get("event") == "post_put_roundtrip" and pid in stored_pids:
            found.append(item)
    assert found, (
        "no post-put round-trip after object bytes were stored on the "
        f"ssh channel: events={events!r}"
    )
    return found[0]


def require_put_step_error(probe: SshTransferProbe) -> dict[str, object]:
    """Require a put-step error packet after version 1 was selected.

    The client must have reached the put step. Handshake-only failure is
    not this event. Missing or unparseable log is a hard failure.
    """
    events = require_version_1_selected(probe)
    by_pid: dict[object, bool] = {}
    found: list[dict[str, object]] = []
    for item in events:
        pid = item.get("pid")
        if item.get("event") == "version_selected":
            by_pid[pid] = True
            continue
        if item.get("event") != "put_error":
            continue
        if not by_pid.get(pid):
            continue
        found.append(item)
    assert found, (
        "session log has no put-step error after version 1 was selected: "
        f"{events!r}"
    )
    return found[0]


def require_no_http_exchanges(
    records: list[RecordedHttpExchange] | None,
) -> None:
    """Require the HTTPS trap recorded no requests at all.

    A missing records object is unclassified. An empty list is absence.
    """
    assert records is not None, (
        "HTTP request log is missing; cannot classify trap contact"
    )
    assert not records, (
        "HTTPS trap was contacted; hybrid family was started: "
        f"{[(rec.method, rec.path) for rec in records]!r}"
    )


def assert_transfer_invocation(
    argv_log: str | Path,
    *,
    repo_path_fragment: str,
    operation: str,
) -> str:
    """Require one GIT_SSH invocation names git-orbulk-transfer, path, operation.

    Same contract as ``require_transfer_invocation``. The name is the
    verdict the suite-bailout audit can see: an empty argv log is not
    a git-orbulk-transfer invocation.
    """
    return require_transfer_invocation(
        argv_log,
        repo_path_fragment=repo_path_fragment,
        operation=operation,
    )


def assert_no_authenticate_invocation(argv_log: str | Path) -> str:
    """Require a readable argv log with no git-orbulk-authenticate line.

    Same contract as ``require_no_authenticate_invocation``. The name is
    the verdict the suite-bailout audit can see: a missing log is not
    classified absence of authenticate.
    """
    return require_no_authenticate_invocation(argv_log)


def assert_version_1_selected(
    probe: SshTransferProbe,
) -> list[dict[str, object]]:
    """Require the session log shows the client selected protocol version 1.

    Same contract as ``require_version_1_selected``. The name is the
    verdict the suite-bailout audit can see: a missing log is not a
    false return.
    """
    return require_version_1_selected(probe)


def assert_ssh_peer_stored(probe: SshTransferProbe, payload: bytes) -> Path:
    """Require the peer store directory holds a file equal to *payload*.

    Same contract as ``require_ssh_peer_stored``. The name is the verdict
    the suite-bailout audit can see: a missing store is not absence of
    the payload.
    """
    return require_ssh_peer_stored(probe, payload)


def assert_ssh_channel_delivered(
    probe: SshTransferProbe, payload: bytes
) -> dict[str, object]:
    """Require the fixture sent *payload* on the SSH channel after version 1.

    Same contract as ``require_ssh_channel_delivered``. The name is the
    verdict the suite-bailout audit can see: handshake-only is not
    channel delivery.
    """
    return require_ssh_channel_delivered(probe, payload)


def assert_post_put_roundtrip(
    probe: SshTransferProbe,
) -> dict[str, object]:
    """Require a same-channel command after object bytes were stored.

    Same contract as ``require_post_put_roundtrip``. The name is the
    verdict the suite-bailout audit can see: a put-only completion is
    not a verified upload.
    """
    return require_post_put_roundtrip(probe)


def assert_no_http_exchanges(
    records: list[RecordedHttpExchange] | None,
) -> None:
    """Require the HTTPS trap recorded no requests at all.

    Same contract as ``require_no_http_exchanges``. The name is the
    verdict the suite-bailout audit can see: any trap contact has
    started the hybrid family.
    """
    require_no_http_exchanges(records)


# ---------------------------------------------------------------------------
# F18: logs / completion / dedup / merge-driver
# ---------------------------------------------------------------------------

PORCELAIN_SUBCOMMANDS: tuple[str, ...] = (
    "checkout",
    "completion",
    "dedup",
    "env",
    "ext",
    "fetch",
    "fsck",
    "install",
    "lock",
    "locks",
    "logs",
    "ls-files",
    "migrate",
    "prune",
    "pull",
    "push",
    "status",
    "track",
    "uninstall",
    "unlock",
    "untrack",
    "update",
    "version",
)

_FICLONE = 0x40049409
_FIEMAP_HEADER_SIZE = 32
_FIEMAP_EXTENT_SIZE = 56
# _IOWR('f', 11, struct fiemap) with sizeof(struct fiemap) == 32
_FS_IOC_FIEMAP = (3 << 30) | (_FIEMAP_HEADER_SIZE << 16) | (ord("f") << 8) | 11
_FIEMAP_FLAG_SYNC = 0x00000001
_FIEMAP_EXTENT_SHARED = 0x00002000
_COW_UNSUPPORTED_ERRNOS = {
    errno.EOPNOTSUPP,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
    errno.EXDEV,
}
_COW_MOUNTS: dict[str, dict[str, str]] = {}
_COW_RELOCATED: set[str] = set()
_LOGS_RESERVED_ENTRIES = frozenset({"last", "show", "clear", "help"})

# Contract: ``logs boomtown`` is the diagnostic-exception sub-entry.
LOGS_DIAGNOSTIC_ENTRY = "boomtown"
_CLONE_NEWNS = 0x00020000
_CLONE_NEWUSER = 0x10000000
_UNSHARED_MOUNT_NS = False
_COW_FSTYPES = frozenset({"xfs", "btrfs", "bcachefs", "ocfs2", "btrfs.zstd"})


def _read_regular_file(path: Path) -> bytes:
    try:
        if not path.is_file():
            raise AssertionError(f"path is not a regular file: {path}")
        return path.read_bytes()
    except FileNotFoundError:
        raise AssertionError(f"path is missing: {path}") from None
    except OSError as exc:
        raise AssertionError(f"cannot read {path}: {exc}") from exc


def _stat_regular_file(path: Path) -> os.stat_result:
    try:
        st = path.stat()
    except FileNotFoundError:
        raise AssertionError(f"path is missing: {path}") from None
    except OSError as exc:
        raise AssertionError(f"cannot stat {path}: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise AssertionError(f"path is not a regular file: {path}")
    return st


def _fiemap_physical_keys(path: Path) -> set[tuple[int, int]]:
    """Physical (offset, length) extents. Failure is unclassified, not empty."""
    count = 64
    buf = bytearray(
        struct.pack(
            "QQIIII",
            0,
            0xFFFFFFFFFFFFFFFF,
            _FIEMAP_FLAG_SYNC,
            0,
            count,
            0,
        )
        + (b"\x00" * (count * _FIEMAP_EXTENT_SIZE))
    )
    try:
        with open(path, "rb") as handle:
            fcntl.ioctl(handle.fileno(), _FS_IOC_FIEMAP, buf)
    except OSError as exc:
        raise AssertionError(f"FIEMAP failed on {path}: {exc}") from exc
    _start, _length, _flags, mapped, _extent_count, _reserved = struct.unpack_from(
        "QQIIII", buf, 0
    )
    keys: set[tuple[int, int]] = set()
    for index in range(mapped):
        off = _FIEMAP_HEADER_SIZE + index * _FIEMAP_EXTENT_SIZE
        logical, physical, length, _r0, _r1, flags, _s0, _s1, _s2 = struct.unpack_from(
            "QQQQQIIII", buf, off
        )
        del logical, flags
        if physical == 0:
            continue
        keys.add((physical, length))
    assert keys, (
        f"FIEMAP returned no physical extents for {path}; "
        f"mapped={mapped} cannot classify sharing"
    )
    return keys


def _share_physical_storage(working: Path, stored: Path) -> bool:
    return bool(_fiemap_physical_keys(working) & _fiemap_physical_keys(stored))


def _run_captured(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(item) for item in argv],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise AssertionError(f"cannot run {list(argv)!r}: {exc}") from exc


def _ensure_mount_capabilities() -> None:
    """Enter a user+mount namespace so loopback mounts can succeed.

    Unprivileged containers lack CAP_SYS_ADMIN. A nested user namespace
    restores it for this process (and children). Process-wide; later COW
    tests reuse the namespace.
    """
    global _UNSHARED_MOUNT_NS
    if _UNSHARED_MOUNT_NS:
        return
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    if libc.unshare(_CLONE_NEWUSER | _CLONE_NEWNS) != 0:
        err = ctypes.get_errno()
        raise AssertionError(
            "unshare(CLONE_NEWUSER|CLONE_NEWNS) failed: "
            f"{os.strerror(err)} (errno {err})"
        )
    try:
        Path("/proc/self/setgroups").write_text("deny")
        Path("/proc/self/uid_map").write_text("0 0 1")
        Path("/proc/self/gid_map").write_text("0 0 1")
    except OSError as exc:
        raise AssertionError(
            f"cannot map uid/gid in the new user namespace: {exc}"
        ) from exc
    _UNSHARED_MOUNT_NS = True


def _umount_cow(mountpoint: str) -> None:
    rec = _COW_MOUNTS.pop(mountpoint, None)
    if rec is None:
        return
    umount = _run_captured(["umount", mountpoint])
    if umount.returncode != 0:
        _run_captured(["umount", "-l", mountpoint])
    loop = rec.get("loop")
    if loop:
        _run_captured(["losetup", "-d", loop])
    image = rec.get("image")
    if image:
        try:
            Path(image).unlink()
        except OSError:
            pass


def _atexit_umount_cow() -> None:
    for mountpoint in list(_COW_MOUNTS):
        _umount_cow(mountpoint)


atexit.register(_atexit_umount_cow)


def independent_cow_supported(directory: Path) -> bool:
    """True when this process can FICLONE inside *directory*.

    EOPNOTSUPP / explicit not-supported is False. Other IO errors raise.
    Does not call the product dedup test-mode switch.
    """
    directory = Path(directory)
    try:
        is_dir = directory.is_dir()
    except OSError as exc:
        raise AssertionError(
            f"cannot classify COW support; cannot stat {directory}: {exc}"
        ) from exc
    assert is_dir, f"COW probe path is not a directory: {directory}"
    tag = token()
    src = directory / f".cow_src_{tag}"
    dst = directory / f".cow_dst_{tag}"
    payload = b"cow-probe-" + tag.encode("ascii") + b"\n"
    try:
        try:
            src.write_bytes(payload)
            dst.write_bytes(b"")
        except OSError as exc:
            raise AssertionError(
                f"cannot write COW probe files in {directory}: {exc}"
            ) from exc
        try:
            with open(src, "rb") as fsrc, open(dst, "r+b") as fdst:
                fcntl.ioctl(fdst.fileno(), _FICLONE, fsrc.fileno())
        except OSError as exc:
            if exc.errno in _COW_UNSUPPORTED_ERRNOS:
                return False
            raise AssertionError(
                f"COW probe ioctl failed in {directory}: {exc}"
            ) from exc
        return True
    finally:
        for path in (src, dst):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise AssertionError(
                    f"cannot remove COW probe file {path}: {exc}"
                ) from exc


def require_cow_clone(working: Path, stored: Path) -> None:
    """Working tree path is a COW clone of the stored object, not a hard link."""
    working = Path(working)
    stored = Path(stored)
    original = _read_regular_file(working)
    stored_bytes = _read_regular_file(stored)
    assert original == stored_bytes, (
        "working tree bytes do not equal the stored object before the "
        f"write probe: working={working} stored={stored}"
    )
    wst = _stat_regular_file(working)
    sst = _stat_regular_file(stored)
    assert (wst.st_dev, wst.st_ino) != (sst.st_dev, sst.st_ino), (
        "working tree and stored object are the same inode; a hard link "
        f"is not a copy-on-write clone: {working} {stored}"
    )
    assert _share_physical_storage(working, stored), (
        "working tree and stored object do not share physical storage; "
        f"not a copy-on-write clone: {working} {stored}"
    )
    probe = b"cow-write-" + token().encode("ascii") + b"\n"
    assert probe != original, "probe bytes collided with the original payload"
    try:
        working.write_bytes(probe)
        after = _read_regular_file(stored)
        assert after == stored_bytes, (
            "writing the working tree changed the stored object; not an "
            f"independently writable clone: {working} {stored}"
        )
    except OSError as exc:
        raise AssertionError(
            f"cannot write working tree {working} for clone probe: {exc}"
        ) from exc
    finally:
        try:
            working.write_bytes(original)
        except OSError as exc:
            raise AssertionError(
                f"cannot restore working tree {working} after clone probe: {exc}"
            ) from exc


def require_not_cow_clone(working: Path, stored: Path) -> None:
    """Working path still holds the payload and is not a COW clone.

    Does not rewrite the working tree on the success path. A hard link
    (same inode) is not an ordinary copy.
    """
    working = Path(working)
    stored = Path(stored)
    working_bytes = _read_regular_file(working)
    stored_bytes = _read_regular_file(stored)
    assert working_bytes == stored_bytes, (
        "working tree is not the stored payload bytes: "
        f"working={working} stored={stored}"
    )
    wst = _stat_regular_file(working)
    sst = _stat_regular_file(stored)
    assert (wst.st_dev, wst.st_ino) != (sst.st_dev, sst.st_ino), (
        "working tree and stored object are the same inode; a hard link "
        f"is not an ordinary checkout copy: {working} {stored}"
    )
    if independent_cow_supported(working.parent) or independent_cow_supported(
        stored.parent
    ):
        assert not _share_physical_storage(working, stored), (
            "working tree still shares physical storage with the stored "
            f"object; this is a copy-on-write clone: {working} {stored}"
        )


def _mkfs_loop_image(image: Path) -> tuple[str, str]:
    """Format *image* as a reflink-capable filesystem. Returns (tool, output)."""
    attempts: list[str] = []
    for tool, extra in (
        ("mkfs.ext4", ["-F", "-q", "-O", "reflink"]),
        ("mke2fs", ["-t", "ext4", "-F", "-q", "-O", "reflink"]),
        ("mkfs.xfs", ["-f", "-q"]),
        ("mkfs.btrfs", ["-f", "-q"]),
    ):
        path = shutil.which(tool)
        if path is None:
            for extra_path in (f"/usr/sbin/{tool}", f"/sbin/{tool}"):
                if Path(extra_path).is_file():
                    path = extra_path
                    break
        if path is None:
            attempts.append(f"{tool}: not found on PATH")
            continue
        result = _run_captured([path, *extra, str(image)])
        blob = (result.stdout or "") + (result.stderr or "")
        attempts.append(
            f"{tool} exit {result.returncode}: {blob.strip() or '(no output)'}"
        )
        if result.returncode == 0:
            return tool, "\n".join(attempts)
    raise AssertionError(
        "could not format a copy-on-write loopback image; "
        f"mkfs/mount transcript:\n" + "\n".join(attempts)
    )


def _unpack_named_cow_fixture(src: Path, image: Path) -> str:
    """Write a vendored filesystem image. Missing fixture is not absence of COW."""
    try:
        blob = src.read_bytes()
    except FileNotFoundError:
        raise AssertionError(
            f"COW filesystem fixture is missing at {src}"
        ) from None
    except OSError as extra:
        raise AssertionError(
            f"cannot read COW filesystem fixture {src}: {extra}"
        ) from extra
    try:
        data = lzma.decompress(blob)
    except lzma.LZMAError as extra:
        raise AssertionError(
            f"COW filesystem fixture {src} is not valid xz: {extra}"
        ) from extra
    assert data, f"COW filesystem fixture decompressed to empty at {src}"
    try:
        image.write_bytes(data)
    except OSError as extra:
        raise AssertionError(
            f"cannot write loopback image {image}: {extra}"
        ) from extra
    return f"fixture {src.name} ({len(data)} bytes)"


def _ensure_loop_devices() -> str:
    """Create /dev/loop-control and loopN nodes when MKNOD is available."""
    lines: list[str] = []
    control = Path("/dev/loop-control")
    if not control.exists():
        try:
            os.mknod(str(control), stat.S_IFCHR | 0o600, os.makedev(10, 237))
            lines.append("created /dev/loop-control")
        except OSError as extra:
            lines.append(f"mknod /dev/loop-control failed: {extra}")
    for index in range(8):
        node = Path(f"/dev/loop{index}")
        if node.exists():
            continue
        try:
            os.mknod(str(node), stat.S_IFBLK | 0o660, os.makedev(7, index))
            lines.append(f"created /dev/loop{index}")
        except OSError as extra:
            lines.append(f"mknod /dev/loop{index} failed: {extra}")
    listing = _run_captured(["ls", "-l", "/dev/loop-control", "/dev/loop0"])
    lines.append(
        f"loop nodes ls exit={listing.returncode} "
        f"{((listing.stdout or '') + (listing.stderr or '')).strip()}"
    )
    return "\n".join(lines)


def _prepare_cow_loop_image(image: Path) -> tuple[str, str]:
    """Format *image* or unpack a vendored reflink image. Returns (fstype, note)."""
    mkfs_error = ""
    try:
        tool, transcript = _mkfs_loop_image(image)
        fstype = "btrfs" if "btrfs" in tool else "xfs" if "xfs" in tool else "ext4"
        return fstype, f"{tool}: {transcript}"
    except AssertionError as extra:
        mkfs_error = str(extra)
    errors: list[str] = [mkfs_error]
    for fstype, name in (
        ("btrfs", "cow_btrfs.img.xz"),
        ("xfs", "cow_xfs.img.xz"),
    ):
        src = Path(__file__).resolve().parent / "_fixtures" / name
        try:
            note = _unpack_named_cow_fixture(src, image)
            return fstype, note
        except AssertionError as extra:
            errors.append(str(extra))
    raise AssertionError(
        "could not prepare a copy-on-write loopback image:\n"
        + "\n".join(errors)
    )


def _libc_mount(
    source: str, target: str, fstype: str, *, options: str = ""
) -> tuple[int, str]:
    """mount(2) without a userspace fs helper. Non-zero is the libc errno."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    data = options.encode() if options else None
    rc = libc.mount(
        source.encode(),
        target.encode(),
        fstype.encode(),
        0,
        data,
    )
    if rc == 0:
        return 0, "ok"
    err = ctypes.get_errno()
    return rc, f"{os.strerror(err)} (errno {err})"


def _try_mount_fs(source: str, mountpoint: Path, fstype: str) -> tuple[int, str]:
    """Try userspace mount(8) then mount(2). Returns (rc, transcript)."""
    lines: list[str] = []
    for argv in (
        ["mount", "-t", fstype, source, str(mountpoint)],
        ["mount", "-t", fstype, "-o", "loop", source, str(mountpoint)],
        ["mount", "-o", "loop", source, str(mountpoint)],
    ):
        result = _run_captured(argv)
        blob = ((result.stdout or "") + (result.stderr or "")).strip()
        lines.append(
            f"{' '.join(argv)} exit {result.returncode}: {blob or '(no output)'}"
        )
        if result.returncode == 0:
            return 0, "\n".join(lines)
    rc, msg = _libc_mount(source, str(mountpoint), fstype)
    lines.append(f"mount(2) {fstype} {source}: {msg}")
    if rc == 0:
        return 0, "\n".join(lines)
    rc_loop, msg_loop = _libc_mount(
        source, str(mountpoint), fstype, options="loop"
    )
    lines.append(f"mount(2) {fstype} loop {source}: {msg_loop}")
    if rc_loop == 0:
        return 0, "\n".join(lines)
    return 1, "\n".join(lines)


def _mount_cow_loopback(mountpoint: Path) -> None:
    """Mount a reflink-capable loopback filesystem on empty *mountpoint*."""
    mountpoint = Path(mountpoint)
    try:
        names = list(os.listdir(mountpoint))
    except OSError as exc:
        raise AssertionError(
            f"cannot list mountpoint {mountpoint}: {exc}"
        ) from exc
    assert not names, (
        f"cannot mount a COW loopback on a non-empty directory {mountpoint}: "
        f"{names!r}"
    )
    try:
        _ensure_mount_capabilities()
    except AssertionError:
        pass
    image = mountpoint.parent / f".cow_image_{token()}"
    try:
        fstype, prepared = _prepare_cow_loop_image(image)
        print(f"cow loop image fstype={fstype} {prepared}")
        print(_ensure_loop_devices())
        losetup = shutil.which("losetup")
        loop_dev = ""
        if losetup is not None:
            shown = _run_captured([losetup, "-f", "--show", str(image)])
            blob_loop = ((shown.stdout or "") + (shown.stderr or "")).strip()
            print(
                f"losetup exit={shown.returncode} out={blob_loop!r}"
            )
            if shown.returncode == 0 and shown.stdout.strip():
                loop_dev = shown.stdout.strip()
        sources = [loop_dev] if loop_dev else []
        sources.append(str(image))
        blob_parts: list[str] = []
        mounted_ok = False
        for source in sources:
            rc, transcript = _try_mount_fs(source, mountpoint, fstype)
            blob_parts.append(transcript)
            if rc == 0:
                mounted_ok = True
                break
        blob = "\n".join(blob_parts)
        if not mounted_ok:
            try:
                _ensure_mount_capabilities()
            except AssertionError as extra:
                blob = blob + f"\nuser-namespace: {extra}"
            else:
                for source in sources:
                    rc, transcript = _try_mount_fs(source, mountpoint, fstype)
                    blob = blob + "\nretry after unshare:\n" + transcript
                    if rc == 0:
                        mounted_ok = True
                        break
        if not mounted_ok:
            if loop_dev:
                _run_captured(["losetup", "-d", loop_dev])
            try:
                image.unlink()
            except OSError:
                pass
            raise AssertionError(
                "could not mount a copy-on-write loopback filesystem; "
                f"mkfs/mount transcript:\n{blob.strip() or '(no output)'}\n"
                f"{_cow_env_transcript()}"
            )
        _COW_MOUNTS[str(mountpoint)] = {
            "image": str(image),
            "loop": loop_dev,
        }
    except AssertionError:
        try:
            image.unlink()
        except OSError:
            pass
        raise


def _cow_env_transcript() -> str:
    """Describe why a loopback mount may be impossible in this process."""
    lines: list[str] = []
    for path in ("/proc/self/status", "/proc/mounts", "/proc/filesystems"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            lines.append(f"{path}: unreadable ({exc})")
            continue
        if path.endswith("status"):
            kept = [
                ln
                for ln in text.splitlines()
                if ln.startswith(("Cap", "NStgid", "Uid", "Gid", "NoNewPrivs"))
            ]
            lines.append(path + ":\n" + "\n".join(kept))
        else:
            lines.append(path + ":\n" + text[:2000])
    return "environment:\n" + "\n".join(lines)


def _existing_cow_parents() -> list[Path]:
    """Writable directories on already-mounted filesystems that FICLONE."""
    found: list[Path] = []
    try:
        text = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError as exc:
        raise AssertionError(f"cannot read /proc/mounts: {exc}") from exc
    seen: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint, fstype = parts[1], parts[2]
        if fstype not in _COW_FSTYPES:
            continue
        path = Path(mountpoint)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            writable = os.access(path, os.W_OK) and path.is_dir()
        except OSError:
            continue
        if not writable:
            continue
        try:
            if independent_cow_supported(path):
                found.append(path)
        except AssertionError:
            continue
    return found


def _relocate_workspace_onto_existing_cow(ws: Workspace) -> Path | None:
    """Point *ws.path* at a subdirectory of an already-mounted COW fs."""
    for parent in _existing_cow_parents():
        dest = parent / f"lfs_cow_{token()}"
        try:
            dest.mkdir(parents=True, exist_ok=False)
        except OSError:
            continue
        if not independent_cow_supported(dest):
            shutil.rmtree(dest, ignore_errors=True)
            continue
        ws.path = dest
        _COW_RELOCATED.add(str(dest))
        print(f"relocated workspace onto existing COW fs at {dest}")
        return dest
    return None


def cow_capable_repo_root(ws: Workspace) -> Path:
    """Return a directory where independent FICLONE succeeds.

    Uses the workspace root when it already supports clone. Otherwise a
    writable directory on an already-mounted copy-on-write filesystem, or
    a reflink loopback mounted on that empty root. Failure to create the
    filesystem is a hard failure, never a skip, and never the product
    dedup test-mode switch.
    """
    root = Path(ws.path)
    if independent_cow_supported(root):
        return root
    relocated = _relocate_workspace_onto_existing_cow(ws)
    if relocated is not None:
        return relocated
    _mount_cow_loopback(root)
    if not independent_cow_supported(root):
        release_cow_filesystem(root)
        raise AssertionError(
            "mounted a loopback filesystem but independent FICLONE still "
            f"reports unsupported at {root}\n{_cow_env_transcript()}"
        )
    return root


def non_cow_repo_root(ws: Workspace) -> Path:
    """Return a directory where independent FICLONE is unsupported.

    Uses the workspace root when the probe is already False. Otherwise a
    tmpfs (or /dev/shm) directory. Probe IO errors are not mapped to
    unsupported.
    """
    root = Path(ws.path)
    if not independent_cow_supported(root):
        return root
    shm = Path("/dev/shm")
    try:
        shm_ok = shm.is_dir()
    except OSError as exc:
        raise AssertionError(f"cannot stat /dev/shm: {exc}") from exc
    if shm_ok:
        dest = shm / f"lfs_nocow_{token()}"
        try:
            dest.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise AssertionError(
                f"cannot create non-COW directory {dest}: {exc}"
            ) from exc
        if not independent_cow_supported(dest):
            return dest
    tmp = Path("/tmp") / f"lfs_nocow_{token()}"
    try:
        tmp.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise AssertionError(
            f"cannot create non-COW directory {tmp}: {exc}"
        ) from exc
    if not independent_cow_supported(tmp):
        return tmp
    raise AssertionError(
        "could not locate a directory where independent FICLONE is "
        f"unsupported (workspace={root}, shm and /tmp both supported clone)"
    )


def release_cow_filesystem(root: Path) -> None:
    """Unmount a loopback created for *root*. No-op when nothing was mounted."""
    key = str(Path(root))
    _umount_cow(key)
    if key in _COW_RELOCATED:
        _COW_RELOCATED.discard(key)
        shutil.rmtree(key, ignore_errors=True)


def invoke_dedup(
    ws: Workspace,
    *,
    test_mode: bool,
    via_git: bool = True,
) -> RunResult:
    """Run ordinary dedup or the filesystem-support test-mode switch."""
    argv = ["dedup"]
    if test_mode:
        argv.append("--test")
    if via_git:
        return ws.invoke_via_git(argv)
    return ws.invoke(argv)


def configure_user_merge_driver(ws: Workspace, attr_name: str) -> None:
    """SET merge.<attr_name>.driver to invoke merge-driver with Git placeholders."""
    assert attr_name, "merge attribute name is empty"
    driver = (
        "git orbulk merge-driver --ancestor %O --current %A "
        "--other %B --marker-size %L --output %A"
    )
    require_git_config_set(ws, f"merge.{attr_name}.driver", driver, local=True)


def set_path_merge_attribute(ws: Workspace, pattern: str, attr_name: str) -> None:
    """Override *pattern*'s merge attribute to *attr_name* after track."""
    assert pattern, "merge attribute pattern is empty"
    assert attr_name, "merge attribute name is empty"
    rel = gitattributes_path()
    existing = gitattributes_bytes_or_missing(ws) or b""
    line = f"{pattern} merge={attr_name}\n".encode("utf-8")
    ws.write(rel, existing + line)
    if pattern.startswith("*."):
        probe = f"probe_{token()}{pattern[1:]}"
    else:
        probe = pattern
    values = git_check_attr(ws, probe, ["merge"])
    assert values["merge"] == attr_name, (
        f"merge attribute for {probe!r} is {values['merge']!r}, not {attr_name!r}"
    )


def logs_list_names(ws: Workspace, *, via_git: bool = True) -> list[str]:
    """Default logs listing. Success with no nonempty lines is an empty list."""
    if via_git:
        result = ws.invoke_via_git(["logs"])
    else:
        result = ws.invoke(["logs"])
    assert result.returncode == 0, (
        "logs listing failed "
        f"(exit {result.returncode}) argv={list(result.argv)!r}: "
        f"{result.stderr_text}"
    )
    return [line.strip() for line in result.stdout_text.splitlines() if line.strip()]


def logs_show_named(ws: Workspace, name: str, *, via_git: bool = True) -> bytes:
    """Show the listed log *name*. Non-zero is not an empty log."""
    assert name, "log name is empty"
    if via_git:
        result = ws.invoke_via_git(["logs", "show", name])
    else:
        result = ws.invoke(["logs", "show", name])
    assert result.returncode == 0, (
        "logs show failed "
        f"(exit {result.returncode}) name={name!r}: {result.stderr_text}"
    )
    return result.stdout


def logs_show_last(ws: Workspace, *, via_git: bool = True) -> bytes:
    """Show the most recent log via ``last``. Non-zero is not an empty log."""
    if via_git:
        result = ws.invoke_via_git(["logs", "last"])
    else:
        result = ws.invoke(["logs", "last"])
    assert result.returncode == 0, (
        "logs last failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result.stdout


def logs_clear(ws: Workspace, *, via_git: bool = True) -> RunResult:
    """Clear stored logs. Subsequent emptiness is asserted by the caller."""
    if via_git:
        result = ws.invoke_via_git(["logs", "clear"])
    else:
        result = ws.invoke(["logs", "clear"])
    assert result.returncode == 0, (
        "logs clear failed "
        f"(exit {result.returncode}): {result.stderr_text}"
    )
    return result


def require_listed_log_file_under_lfs_namespace(
    ws: Workspace, name: str
) -> Path:
    """Require a file named *name* exists under the repository LFS namespace."""
    assert name, "listed log name is empty"
    root = git_dir(ws) / "lfs"
    try:
        is_dir = root.is_dir()
    except OSError as exc:
        raise AssertionError(
            f"cannot classify the LFS namespace at {root}: {exc}"
        ) from exc
    assert is_dir, (
        f"LFS namespace is missing at {root}; no log directory was created"
    )
    found: list[Path] = []
    seen: list[str] = []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                seen.append(filename)
                if filename == name:
                    found.append(Path(dirpath) / filename)
    except OSError as exc:
        raise AssertionError(
            f"cannot walk LFS namespace {root}: {exc}"
        ) from exc
    assert found, (
        f"no file named {name!r} under {root}; saw {seen!r}"
    )
    return found[0]


def emit_completion_script(ws: Workspace, shell: str) -> bytes:
    """Emit a non-empty completion script for *shell*. Non-zero is not empty."""
    assert shell in ("bash", "fish", "zsh"), (
        f"completion shell must be bash, fish, or zsh, got {shell!r}"
    )
    result = ws.invoke_via_git(["completion", shell])
    assert result.returncode == 0, (
        "completion script emission failed "
        f"(exit {result.returncode}) shell={shell!r}: {result.stderr_text}"
    )
    assert result.stdout, (
        f"completion {shell} emitted an empty script; stderr={result.stderr_text!r}"
    )
    return result.stdout


def _normalize_completion_candidate(raw: str) -> str:
    text = raw.split("\t", 1)[0].strip()
    if text.startswith("-") and ":" in text:
        text = text.split(":", 1)[0]
    return text


def _command_line_for_words(words: Sequence[str]) -> str:
    items = [str(item) for item in words]
    if not items:
        return ""
    if items[-1] == "":
        return " ".join(items[:-1]) + " "
    return " ".join(items)


def _which_or_fail(name: str) -> str:
    path = shutil.which(name)
    assert path, f"{name} is not installed; cannot load a completion script"
    return path


def _git_bash_completion_script() -> Path:
    exec_path_run = _run_captured(["git", "--exec-path"])
    assert exec_path_run.returncode == 0, (
        "git --exec-path failed "
        f"(exit {exec_path_run.returncode}): {exec_path_run.stderr}"
    )
    exec_path = exec_path_run.stdout.strip()
    assert exec_path, "git --exec-path produced no path"
    candidates = [
        Path("/usr/share/bash-completion/completions/git"),
        Path("/usr/share/git-core/contrib/completion/git-completion.bash"),
        Path(exec_path) / "git-completion.bash",
        Path(exec_path).parent.parent
        / "share/git-core/contrib/completion/git-completion.bash",
        Path("/etc/bash_completion.d/git"),
    ]
    errors: list[str] = []
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    raise AssertionError(
        "no installed Git bash completion script; "
        f"tried {candidates!r} errors={errors!r}"
    )


def _bash_completion_driver() -> str:
    return r"""
set +e
_get_comp_words_by_ref() {
    cur="${COMP_WORDS[COMP_CWORD]}"
    if (( COMP_CWORD > 0 )); then
        prev="${COMP_WORDS[COMP_CWORD-1]}"
    else
        prev=""
    fi
    words=("${COMP_WORDS[@]}")
    cword=$COMP_CWORD
}
SCRIPT="$1"
WORDS_FILE="$2"
GIT_COMP="$3"
if [ -n "$GIT_COMP" ]; then
    # shellcheck disable=SC1090
    . "$GIT_COMP"
fi
# shellcheck disable=SC1090
. "$SCRIPT"
mapfile -t COMP_WORDS < "$WORDS_FILE"
COMP_CWORD=$((${#COMP_WORDS[@]} - 1))
COMP_LINE=""
for ((i=0; i<${#COMP_WORDS[@]}; i++)); do
    if (( i > 0 )); then
        COMP_LINE+=" "
    fi
    COMP_LINE+="${COMP_WORDS[i]}"
done
COMP_POINT=${#COMP_LINE}
COMPREPLY=()
COMP_TYPE=9
compopt() { return 0; }
_filedir() { return 0; }
if [ -n "$GIT_COMP" ] && declare -F _git >/dev/null; then
    _git
elif declare -F _git_orbulk >/dev/null; then
    _git_orbulk
else
    __start_git-orbulk
fi
printf '%s\n' "${COMPREPLY[@]}"
"""


def _fish_completion_driver() -> str:
    return r"""
set -g fish_greeting
source $argv[1]
complete -C "$argv[2]"
"""


def _zsh_completion_driver() -> str:
    return r"""
setopt no_aliases
SCRIPT=$1
WORDS_FILE=$2
if [[ -n ${PATH_PREFIX:-} ]]; then
    PATH="$PATH_PREFIX:$PATH"
    export PATH
    rehash
fi
compdef() { return 0 }
_arguments() { return 1 }
typeset -ga CAPTURED
_describe() {
    integer i
    for i in {1..$#}; do
        if [[ ${argv[i]} == "--" ]]; then
            (( i++ ))
            CAPTURED+=("${argv[i,-1]}")
            return 0
        fi
    done
    if (( ${#completions} )); then
        CAPTURED+=("${completions[@]}")
    fi
    return 0
}
compadd() {
    integer i=1
    while (( i <= $# )); do
        case ${argv[i]} in
            --)
                (( i++ ))
                CAPTURED+=("${argv[i,-1]}")
                break
                ;;
            -a|-d|-X|-J|-V|-S|-P|-r|-R|-s|-W|-M|-O|-A|-D|-E|-q)
                (( i += 2 ))
                ;;
            -*)
                (( i++ ))
                ;;
            *)
                CAPTURED+=("${argv[i]}")
                (( i++ ))
                ;;
        esac
    done
    return 0
}
source $SCRIPT
typeset -ga words
words=()
while IFS= read -r line || [[ -n $line ]]; do
    words+=("$line")
done < $WORDS_FILE
CURRENT=$#words
_git-orbulk
print -l -- "${CAPTURED[@]}"
"""


def completion_candidates(
    ws: Workspace,
    *,
    shell: str,
    script: bytes,
    words: Sequence[str],
    git_completion: bool = False,
) -> list[str]:
    """Load *script* in *shell* and return completion tokens for *words*.

    Load failure, a missing shell, or a completion-function error is a
    hard failure, never an empty candidate list. Does not invoke the
    hidden completion interface from Python.
    """
    assert shell in ("bash", "fish", "zsh"), (
        f"completion shell must be bash, fish, or zsh, got {shell!r}"
    )
    assert script, "completion script is empty; cannot load it"
    assert words, "completion words are empty"
    if git_completion:
        assert shell == "bash", (
            "git_completion is only defined for bash, "
            f"got shell={shell!r}"
        )
    interpreter = _which_or_fail(shell)
    tag = token()
    script_rel = f"comp_script_{tag}.{shell}"
    words_rel = f"comp_words_{tag}.txt"
    driver_rel = f"comp_drv_{tag}"
    out_path = ws.resolve(script_rel)
    ws.write(script_rel, script)
    words_text = "".join(f"{item}\n" for item in words)
    ws.write(words_rel, words_text)
    env = dict(ws.env)
    bin_dir = str(product_bin_dir().resolve())
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["PATH_PREFIX"] = bin_dir
    debug_rel = f"comp_debug_{tag}.log"
    ws.write(debug_rel, "")
    env["BASH_COMP_DEBUG_FILE"] = str(ws.resolve(debug_rel))
    git_comp = ""
    if shell == "bash":
        driver = _bash_completion_driver()
        argv = [interpreter, "--noprofile", "--norc", ws.resolve(driver_rel).as_posix()]
        extra = [
            str(ws.resolve(script_rel)),
            str(ws.resolve(words_rel)),
        ]
        if git_completion:
            git_comp = str(_git_bash_completion_script())
        extra.append(git_comp)
        argv.extend(extra)
        ws.write(driver_rel, driver)
    elif shell == "fish":
        driver = _fish_completion_driver()
        cmdline = _command_line_for_words(words)
        ws.write(driver_rel, driver)
        argv = [
            interpreter,
            "--no-config",
            str(ws.resolve(driver_rel)),
            str(ws.resolve(script_rel)),
            cmdline,
        ]
    else:
        driver = _zsh_completion_driver()
        ws.write(driver_rel, driver)
        env["ZDOTDIR"] = str(ws.home)
        argv = [
            interpreter,
            "-f",
            str(ws.resolve(driver_rel)),
            str(ws.resolve(script_rel)),
            str(ws.resolve(words_rel)),
        ]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ws.path),
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"{shell} completion timed out argv={argv!r}: {exc}"
        ) from exc
    except OSError as exc:
        raise AssertionError(
            f"cannot run {shell} to load completion script {out_path}: {exc}"
        ) from exc
    assert proc.returncode == 0, (
        f"{shell} failed to load the emitted completion script "
        f"(exit {proc.returncode}) argv={argv!r} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    candidates: list[str] = []
    for line in proc.stdout.splitlines():
        token_name = _normalize_completion_candidate(line)
        if token_name:
            candidates.append(token_name)
    print(
        f"completion shell={shell} git_completion={git_completion} "
        f"words={list(words)!r} n={len(candidates)} sample={candidates[:12]!r} "
        f"stderr={proc.stderr[:500]!r}"
    )
    if not candidates:
        debug_path = Path(env.get("BASH_COMP_DEBUG_FILE") or "")
        debug_text = ""
        if debug_path:
            try:
                debug_text = debug_path.read_text(encoding="utf-8")
            except OSError as exc:
                debug_text = f"(unreadable: {exc})"
        print(f"{shell} completion debug log: {debug_text!r}")
    return candidates


def require_porcelain_subcommand_candidates(candidates: Sequence[str]) -> list[str]:
    """Require each PRD command inventory porcelain name appears as its own candidate token."""
    have = set(candidates)
    missing = [name for name in PORCELAIN_SUBCOMMANDS if name not in have]
    assert not missing, (
        "completion candidates are missing porcelain subcommand names "
        f"{missing!r}; got {list(candidates)!r}"
    )
    return list(candidates)


def assert_porcelain_subcommand_candidates(candidates: Sequence[str]) -> list[str]:
    """Require each PRD command inventory porcelain name appears as its own candidate token.

    Same contract as ``require_porcelain_subcommand_candidates``. The name
    is the verdict the suite-bailout audit can see: a script that loads
    but yields no porcelain names has not completed the standalone (or
    git-invoked) entry.
    """
    return require_porcelain_subcommand_candidates(candidates)


def require_clone_among_porcelain_candidates(
    candidates: Sequence[str],
) -> list[str]:
    """Require clone appears as its own porcelain candidate token.

    PRD command inventory lists clone as porcelain. FP-18's porcelain-candidate set is that
    inventory, observed through the shell's use of the emitted script.
    """
    assert "clone" in set(candidates), (
        "completion candidates are missing porcelain subcommand name "
        f"'clone'; got {list(candidates)!r}"
    )
    return list(candidates)


def assert_clone_among_porcelain_candidates(
    candidates: Sequence[str],
) -> list[str]:
    """Require clone appears as its own porcelain candidate token.

    Same contract as ``require_clone_among_porcelain_candidates``. The name
    is the verdict the suite-bailout audit can see: a script that loads
    and yields other porcelain names but omits clone has not completed
    the standalone (or git-invoked) porcelain-candidate set.
    """
    return require_clone_among_porcelain_candidates(candidates)


def require_flag_shaped_candidates(
    candidates: Sequence[str],
    *,
    unlike: Sequence[str],
) -> list[str]:
    """Require candidates unlike *unlike*, with a leftover dash-prefix token."""
    unlike_set = set(unlike)
    extra = [item for item in candidates if item not in unlike_set]
    dash = [
        item
        for item in extra
        if item.startswith("-") and item not in ("-", "--")
    ]
    assert extra, (
        "candidates were not distinguishable from the unlike set "
        f"unlike={list(unlike)!r} candidates={list(candidates)!r}"
    )
    assert dash, (
        "no dash-prefix remainder after removing the unlike set "
        f"extra={extra!r} candidates={list(candidates)!r}"
    )
    return dash


def require_omits_token(candidates: Sequence[str], name: str) -> list[str]:
    """Require *name* is absent from the candidate list."""
    assert name, "omit token is empty"
    assert name not in candidates, (
        f"completion candidates unexpectedly include {name!r}: "
        f"{list(candidates)!r}"
    )
    return list(candidates)


def _shell_bash_completion_driver() -> str:
    """Load a bash completion script the way bash's complete builtin uses it."""
    return r"""
set +e
_get_comp_words_by_ref() {
    cur="${COMP_WORDS[COMP_CWORD]}"
    if (( COMP_CWORD > 0 )); then
        prev="${COMP_WORDS[COMP_CWORD-1]}"
    else
        prev=""
    fi
    words=("${COMP_WORDS[@]}")
    cword=$COMP_CWORD
}
SCRIPT="$1"
WORDS_FILE="$2"
GIT_COMP="$3"
if [ -n "$GIT_COMP" ]; then
    # shellcheck disable=SC1090
    . "$GIT_COMP"
fi
# shellcheck disable=SC1090
. "$SCRIPT"
mapfile -t COMP_WORDS < "$WORDS_FILE"
COMP_CWORD=$((${#COMP_WORDS[@]} - 1))
COMP_LINE=""
for ((i=0; i<${#COMP_WORDS[@]}; i++)); do
    if (( i > 0 )); then
        COMP_LINE+=" "
    fi
    COMP_LINE+="${COMP_WORDS[i]}"
done
COMP_POINT=${#COMP_LINE}
COMPREPLY=()
COMP_TYPE=9
compopt() { return 0; }
_filedir() { return 0; }
if [ -n "$GIT_COMP" ] && declare -F _git >/dev/null; then
    _git
else
    cmd="${COMP_WORDS[0]}"
    spec=""
    if complete -p -- "$cmd" >/dev/null 2>&1; then
        spec=$(complete -p -- "$cmd")
    else
        base=$(basename -- "$cmd")
        if complete -p -- "$base" >/dev/null 2>&1; then
            spec=$(complete -p -- "$base")
        fi
    fi
    func=""
    prev=""
    for tok in $spec; do
        if [ "$prev" = "-F" ]; then
            func="$tok"
            break
        fi
        prev="$tok"
    done
    if [ -z "$func" ]; then
        echo "no bash complete -F registration for $cmd (spec=${spec})" >&2
        exit 1
    fi
    if ! declare -F "$func" >/dev/null; then
        echo "bash complete registered $func for $cmd but that function is not defined" >&2
        exit 1
    fi
    "$func"
fi
printf '%s\n' "${COMPREPLY[@]}"
"""


def _shell_zsh_completion_driver() -> str:
    """Load a zsh completion script the way zsh's compdef registry uses it."""
    return r"""
setopt no_aliases
SCRIPT=$1
WORDS_FILE=$2
if [[ -n ${PATH_PREFIX:-} ]]; then
    PATH="$PATH_PREFIX:$PATH"
    export PATH
    rehash
fi
DUMP="${ZDOTDIR:-$HOME}/.zcompdump"
if ! autoload -Uz compinit; then
    print -u2 "zsh autoload compinit failed"
    exit 1
fi
if ! compinit -u -d "$DUMP"; then
    print -u2 "zsh compinit failed dump=$DUMP"
    exit 1
fi
typeset -ga CAPTURED
_arguments() {
    integer i
    local spec inner w rest flag
    for (( i = 1; i <= $#; i++ )); do
        spec="${argv[i]}"
        case $spec in
            -*)
                continue
                ;;
        esac
        if [[ "$spec" == *'('*')'* ]]; then
            inner="${spec#*\(}"
            inner="${inner%%)*}"
            for w in ${(z)inner}; do
                [[ -z "$w" || "$w" == _* ]] && continue
                CAPTURED+=("$w")
            done
        fi
        rest="$spec"
        while [[ "$rest" == *--[A-Za-z]* ]]; do
            rest="${rest#*--}"
            flag="--${rest%%[^A-Za-z0-9_-]*}"
            if [[ -n "$flag" && "$flag" != "--" ]]; then
                CAPTURED+=("$flag")
            fi
            rest="${rest#"${flag#--}"}"
        done
    done
    return 0
}
_describe() {
    integer i
    for i in {1..$#}; do
        if [[ ${argv[i]} == "--" ]]; then
            (( i++ ))
            CAPTURED+=("${argv[i,-1]}")
            return 0
        fi
    done
    if (( ${#completions} )); then
        CAPTURED+=("${completions[@]}")
    fi
    return 0
}
compadd() {
    integer i=1
    while (( i <= $# )); do
        case ${argv[i]} in
            --)
                (( i++ ))
                CAPTURED+=("${argv[i,-1]}")
                break
                ;;
            -a|-d|-X|-J|-V|-S|-P|-r|-R|-s|-W|-M|-O|-A|-D|-E|-q)
                (( i += 2 ))
                ;;
            -*)
                (( i++ ))
                ;;
            *)
                CAPTURED+=("${argv[i]}")
                (( i++ ))
                ;;
        esac
    done
    return 0
}
source $SCRIPT
typeset -ga words
words=()
while IFS= read -r line || [[ -n $line ]]; do
    words+=("$line")
done < $WORDS_FILE
CURRENT=$#words
cmd=${words[1]}
completer=${_comps[$cmd]}
if [[ -z $completer ]]; then
    completer=${_comps[${cmd:t}]}
fi
if [[ -z $completer ]]; then
    print -u2 "no zsh compdef registration for $cmd; _comps keys=${(k)_comps}"
    exit 1
fi
"$completer"
print -l -- "${CAPTURED[@]}"
"""


def shell_completion_candidates(
    ws: Workspace,
    *,
    shell: str,
    script: bytes,
    words: Sequence[str],
    git_completion: bool = False,
) -> list[str]:
    """Load *script* in *shell* the way that shell uses it; return candidates.

    Bash: after sourcing, invoke the function registered with ``complete -F``
    for the command (or Git's ``_git`` when Git completion is active).
    Zsh: after ``compinit`` and sourcing, invoke the completer registered in
    ``_comps``. Does not pin completer function names, and does not stub
    zsh ``_arguments`` to fail. Load failure is a hard failure, never an
    empty candidate list. Does not invoke a hidden completion interface
    from Python.
    """
    assert shell in ("bash", "fish", "zsh"), (
        f"completion shell must be bash, fish, or zsh, got {shell!r}"
    )
    assert script, "completion script is empty; cannot load it"
    assert words, "completion words are empty"
    if git_completion:
        assert shell == "bash", (
            "git_completion is only defined for bash, "
            f"got shell={shell!r}"
        )
    interpreter = _which_or_fail(shell)
    tag = token()
    script_rel = f"comp_script_{tag}.{shell}"
    words_rel = f"comp_words_{tag}.txt"
    driver_rel = f"comp_drv_{tag}"
    out_path = ws.resolve(script_rel)
    ws.write(script_rel, script)
    words_text = "".join(f"{item}\n" for item in words)
    ws.write(words_rel, words_text)
    env = dict(ws.env)
    bin_dir = str(product_bin_dir().resolve())
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["PATH_PREFIX"] = bin_dir
    debug_rel = f"comp_debug_{tag}.log"
    ws.write(debug_rel, "")
    env["BASH_COMP_DEBUG_FILE"] = str(ws.resolve(debug_rel))
    git_comp = ""
    if shell == "bash":
        driver = _shell_bash_completion_driver()
        argv = [interpreter, "--noprofile", "--norc", ws.resolve(driver_rel).as_posix()]
        extra = [
            str(ws.resolve(script_rel)),
            str(ws.resolve(words_rel)),
        ]
        if git_completion:
            git_comp = str(_git_bash_completion_script())
        extra.append(git_comp)
        argv.extend(extra)
        ws.write(driver_rel, driver)
    elif shell == "fish":
        driver = _fish_completion_driver()
        cmdline = _command_line_for_words(words)
        ws.write(driver_rel, driver)
        argv = [
            interpreter,
            "--no-config",
            str(ws.resolve(driver_rel)),
            str(ws.resolve(script_rel)),
            cmdline,
        ]
    else:
        driver = _shell_zsh_completion_driver()
        ws.write(driver_rel, driver)
        env["ZDOTDIR"] = str(ws.home)
        argv = [
            interpreter,
            "-f",
            str(ws.resolve(driver_rel)),
            str(ws.resolve(script_rel)),
            str(ws.resolve(words_rel)),
        ]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ws.path),
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"{shell} completion timed out argv={argv!r}: {exc}"
        ) from exc
    except OSError as exc:
        raise AssertionError(
            f"cannot run {shell} to load completion script {out_path}: {exc}"
        ) from exc
    assert proc.returncode == 0, (
        f"{shell} failed to load the emitted completion script "
        f"(exit {proc.returncode}) argv={argv!r} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    candidates: list[str] = []
    for line in proc.stdout.splitlines():
        token_name = _normalize_completion_candidate(line)
        if token_name:
            candidates.append(token_name)
    print(
        f"shell_completion shell={shell} git_completion={git_completion} "
        f"words={list(words)!r} n={len(candidates)} sample={candidates[:12]!r} "
        f"stderr={proc.stderr[:500]!r}"
    )
    if not candidates:
        debug_path = Path(env.get("BASH_COMP_DEBUG_FILE") or "")
        debug_text = ""
        if debug_path:
            try:
                debug_text = debug_path.read_text(encoding="utf-8")
            except OSError as extra:
                debug_text = f"(unreadable: {extra})"
        print(f"{shell} completion debug log: {debug_text!r}")
    return candidates


def _zsh_fpath_script_basename(script: bytes, command: str) -> str:
    """Return a fpath completion filename for *script* completing *command*.

    Uses a ``#compdef`` header when present. Does not pin a completer
    function name.
    """
    text = script.decode("utf-8", errors="replace")
    first = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            first = stripped
            break
    name = Path(command).name
    if first.startswith("#compdef"):
        rest = first[len("#compdef") :].strip()
        if rest:
            name = Path(rest.split()[0]).name
    assert name, "zsh fpath completion filename is empty"
    if not name.startswith("_"):
        name = "_" + name
    return name


def _strip_term_controls(text: str) -> str:
    """Remove CR and CSI sequences from a tty listing. Not a candidate oracle."""
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", cleaned)
    cleaned = re.sub(r"\x1b.", "", cleaned)
    return cleaned


def _fpath_zsh_inner_setup() -> str:
    """fpath + compinit setup. Asks zsh to complete; does not wrap builtins."""
    return r"""
setopt zle
setopt no_aliases no_beep no_list_beep
unsetopt prompt_cr prompt_sp
# List candidates even when zsh first inserts an unambiguous common prefix
# (a typed "-" that every flag candidate extends to "--"); without this,
# such a completion inserts the prefix and shows no list.
setopt auto_list
unsetopt list_ambiguous
PROMPT='---ZSHPROMPT---'
RPROMPT=
PROMPT2=
PROMPT3=
PROMPT4=
SPROMPT=
export PATH
rehash
fpath=(${ZSH_FPATH_DIR} $fpath)
autoload -Uz compinit
if ! compinit -u -d ${ZDOTDIR:-$HOME}/.zcompdump_fpath; then
  print -r -- 'compinit-failed'
  exit 1
fi
for _compfile in ${ZSH_FPATH_DIR}/_*(N); do
  builtin source $_compfile
done
bindkey '^M' undefined-key
bindkey '^J' undefined-key
bindkey '^I' complete-word
_comp_mark() {
  print -r -- '---COMPSTART---'
}
_comp_finish() {
  print -r -- '---COMPEND---'
}
compprefuncs=( _comp_mark )
comppostfuncs=( _comp_finish )
zstyle ':completion:*' list-grouped false
zstyle ':completion:*' insert-tab false
zstyle ':completion:*' list-separator ''
zstyle ':completion:*' menu false
zstyle ':completion:*' force-list always
zstyle ':completion:*' verbose false
zstyle ':completion:*' extra-verbose false
zstyle ':completion:*' format ''
zstyle ':completion:*' group-name ''
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' list-prompt ''
zstyle ':completion:*' select-prompt ''
LISTMAX=0
COLUMNS=120
LINES=80
"""


def _pty_read_until(
    master: int,
    collected: bytearray,
    needle: bytes,
    *,
    deadline: float,
) -> None:
    """Read *master* into *collected* until *needle* appears or *deadline*."""
    while needle not in collected:
        remaining = deadline - time.time()
        if remaining <= 0:
            text = _strip_term_controls(
                collected.decode("utf-8", errors="replace")
            )
            raise AssertionError(
                f"zsh fpath completion timed out waiting for {needle!r}; "
                f"transcript={text[-2000:]!r}"
            )
        ready, _, _ = select.select([master], [], [], min(remaining, 0.25))
        if not ready:
            continue
        try:
            chunk = os.read(master, 4096)
        except OSError as extra:
            if extra.errno in (errno.EIO, errno.EAGAIN):
                text = _strip_term_controls(
                    collected.decode("utf-8", errors="replace")
                )
                raise AssertionError(
                    f"zsh fpath pty closed waiting for {needle!r}; "
                    f"transcript={text[-2000:]!r}"
                ) from extra
            raise AssertionError(
                f"zsh fpath pty read failed: {extra}"
            ) from extra
        if not chunk:
            text = _strip_term_controls(
                collected.decode("utf-8", errors="replace")
            )
            raise AssertionError(
                f"zsh fpath pty EOF waiting for {needle!r}; "
                f"transcript={text[-2000:]!r}"
            )
        collected.extend(chunk)


def fpath_zsh_completion_candidates(
    ws: Workspace,
    *,
    script: bytes,
    words: Sequence[str],
) -> list[str]:
    """Load *script* on zsh fpath and return candidates zsh itself completes.

    Places the emitted script on fpath so ``compinit`` honours a
    ``#compdef`` header, then asks zsh to complete the command line.
    Does not require a source-time ``_comps`` registration and does not
    intercept ``_arguments``, ``_describe``, or ``compadd``. Load
    failure is a hard failure, never an empty candidate list.
    """
    assert script, "completion script is empty; cannot load it"
    assert words, "completion words are empty"
    interpreter = _which_or_fail("zsh")
    tag = token()
    fpath_rel = f"zsh_fpath_{tag}"
    fpath_dir = ws.resolve(fpath_rel)
    try:
        fpath_dir.mkdir(parents=True, exist_ok=False)
    except OSError as extra:
        raise AssertionError(
            f"cannot create zsh fpath directory {fpath_dir}: {extra}"
        ) from extra
    basename = _zsh_fpath_script_basename(script, str(words[0]))
    inner_path = fpath_dir / ".inner_setup.zsh"
    try:
        (fpath_dir / basename).write_bytes(script)
        inner_path.write_text(_fpath_zsh_inner_setup(), encoding="utf-8")
    except OSError as extra:
        raise AssertionError(
            f"cannot write zsh fpath completion files under {fpath_dir}: {extra}"
        ) from extra
    cmdline = _command_line_for_words(words)
    env = dict(ws.env)
    bin_dir = str(product_bin_dir().resolve())
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["PATH_PREFIX"] = bin_dir
    env["ZDOTDIR"] = str(ws.home)
    env["ZSH_FPATH_DIR"] = str(fpath_dir)
    env["TERM"] = "xterm"
    env["COLUMNS"] = "120"
    env["LINES"] = "40"
    debug_rel = f"comp_fpath_debug_{tag}.log"
    ws.write(debug_rel, "")
    env["BASH_COMP_DEBUG_FILE"] = str(ws.resolve(debug_rel))
    pid, master = pty.fork()
    if pid == 0:
        try:
            os.chdir(str(ws.path))
        except OSError:
            os._exit(127)
        try:
            os.execve(interpreter, [interpreter, "-f", "-i"], env)
        except OSError:
            os._exit(127)
    collected = bytearray()
    deadline = time.time() + 25
    try:
        started = time.time()
        while time.time() - started < 2.0:
            ready, _, _ = select.select([master], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            collected.extend(chunk)
            if b"%" in collected or b"#" in collected:
                break
        os.write(master, f"builtin source {inner_path.as_posix()}\n".encode())
        _pty_read_until(master, collected, b"---ZSHPROMPT---", deadline=deadline)
        time.sleep(0.05)
        os.write(master, cmdline.encode("utf-8"))
        time.sleep(0.05)
        os.write(master, b"\t")
        _pty_read_until(master, collected, b"---COMPSTART---", deadline=deadline)
        idle_until = time.time() + 0.8
        hard_until = time.time() + 3.0
        while time.time() < idle_until and time.time() < hard_until:
            ready, _, _ = select.select([master], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            collected.extend(chunk)
            idle_until = time.time() + 0.4
        try:
            os.write(master, b"\x03")
        except OSError:
            pass
        try:
            os.write(master, b"\x04")
        except OSError:
            pass
    except AssertionError:
        try:
            os.write(master, b"\x04")
        except OSError:
            pass
        raise
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
    blob = _strip_term_controls(collected.decode("utf-8", errors="replace"))
    start = blob.find("---COMPSTART---")
    assert start != -1, (
        "zsh fpath completion did not start a listing; "
        f"transcript={blob[-2000:]!r}"
    )
    listing = blob[start + len("---COMPSTART---") :]
    skip = {
        "---COMPSTART---",
        "---COMPEND---",
        "---ZSHPROMPT---",
        "builtin",
        "source",
    }
    candidates: list[str] = []
    for raw in listing.split():
        token_name = _normalize_completion_candidate(raw)
        if token_name and token_name not in skip:
            candidates.append(token_name)
    print(
        f"fpath_zsh words={list(words)!r} n={len(candidates)} "
        f"sample={candidates[:12]!r} listing={listing[:500]!r}"
    )
    if not candidates:
        debug_text = ""
        try:
            debug_text = Path(env["BASH_COMP_DEBUG_FILE"]).read_text(
                encoding="utf-8"
            )
        except OSError as extra:
            debug_text = f"(unreadable: {extra})"
        print(f"fpath_zsh debug log: {debug_text[-1500:]!r}")
        print(f"fpath_zsh transcript: {blob[-1500:]!r}")
    return candidates


def fpath_shell_completion_candidates(
    ws: Workspace,
    *,
    shell: str,
    script: bytes,
    words: Sequence[str],
    git_completion: bool = False,
) -> list[str]:
    """Load *script* the way *shell* uses it; return completion candidates.

    Zsh: place the script on fpath and ask zsh to complete. Bash/fish:
    the same load-and-complete path as ``shell_completion_candidates``.
    """
    if shell == "zsh":
        assert not git_completion, (
            "git_completion is only defined for bash, got shell='zsh'"
        )
        return fpath_zsh_completion_candidates(
            ws, script=script, words=words
        )
    return shell_completion_candidates(
        ws,
        shell=shell,
        script=script,
        words=words,
        git_completion=git_completion,
    )


def call_named_logs_diagnostic_exception(ws: Workspace) -> str:
    """Invoke the diagnostic-exception logs sub-entry so it fails and a log appears.

    The sub-entry is the Contract's ``logs boomtown``. It must exit
    non-zero and the default listing must then name a log that was not
    listed before. Returns the sub-entry spelling for later invokes.
    """
    name = LOGS_DIAGNOSTIC_ENTRY
    before = logs_list_names(ws)
    result = ws.invoke_via_git(["logs", name])
    print(f"logs diagnostic entry {name!r} exit={result.returncode}")
    assert result.returncode != 0, (
        f"logs {name} succeeded; the diagnostic exception must fail: "
        f"{result.stdout_text!r} {result.stderr_text!r}"
    )
    after = logs_list_names(ws)
    added = [item for item in after if item not in before]
    assert added, (
        f"logs {name} failed but added no listed log; "
        f"before={before!r} after={after!r}"
    )
    return name


@contextmanager
def delayed_download_batch_server(
    *,
    delay_seconds: float,
    payloads: Sequence[bytes],
) -> Iterator[ConformingBatchServer]:
    """Loopback batch+basic download whose GET body is delayed.

    Negotiation is immediate. The download action waits *delay_seconds*
    after headers before writing object bytes so an activity timeout
    shorter than that delay can fire. Not a rewrite of
    ``conforming_batch_server``.
    """
    assert delay_seconds >= 0, (
        f"delay_seconds must be non-negative, got {delay_seconds!r}"
    )
    payload_list = list(payloads)
    assert payload_list, "delayed_download_batch_server needs payloads"
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()
    state = {"max_in_flight": 0, "in_flight": 0}

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = _batch_headers_dict(self)
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(
            self, body: bytes, headers: dict[str, str]
        ) -> None:
            accept = _header_ci(headers, "Accept")
            content_type = _header_ci(headers, "Content-Type")
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    _send_bytes(self, 400, b"")
                    return
                oid = str(raw.get("oid") or "")
                try:
                    size = int(raw.get("size"))
                except (TypeError, ValueError):
                    _send_bytes(self, 400, b"")
                    return
                item: dict[str, object] = {
                    "oid": oid,
                    "size": size,
                    "authenticated": True,
                }
                href_oid = oid if oid in action_paths else None
                if href_oid is None and action_paths:
                    href_oid = next(iter(action_paths))
                if href_oid is not None and operation == "download":
                    href = "http://placeholder" + action_paths[href_oid]
                    item["actions"] = {
                        "download": {
                            "href": href,
                            "header": {hdr_name: hdr_value},
                        }
                    }
                reply_objects.append(item)
            origin = _origin_for_handler(self)
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            data = by_oid[oid]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command == "HEAD":
                return
            self.wfile.flush()
            if delay_seconds:
                time.sleep(delay_seconds)
            self.wfile.write(data)
            self.wfile.flush()

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with loopback_http(Handler) as svc:
        yield ConformingBatchServer(
            url=svc.url,
            records=records,
            header_name=hdr_name,
            header_value=hdr_value,
            action_paths=action_paths,
            verify_paths={},
            payloads=by_oid,
            state=state,
        )


