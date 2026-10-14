# feature: F02
"""Observation helpers for the membundle bootstrap command (FP-02).

Every public name here is an observation of files or of a ``RunResult``
from ``membundle bootstrap``. Helpers raise ``HarnessError`` when a query cannot
be classified, and ``AssertionError`` when a classified observation misses
a carrier the tests require. They never return ``None`` / ``{}`` / ``""``
to mean "could not look".
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path

from _harness import (
    HarnessError,
    RunResult,
    Workspace,
    path_is_dir,
    path_is_file,
    read_bytes,
    read_file,
    utc_today_iso,
)
from F01_helpers import (
    assert_index_structure,
    combined_report,
    first_heading_text,
    split_yaml_frontmatter,
    stage_writable_sources,
    utc_dates_spanning_invoke,
)

# Exact HTML delimiter comments named by the PRD.
BEGIN_MEMBUNDLE_COMMENT = "<!-- BEGIN MEMBUNDLE AGENT MEMORY -->"
END_MEMBUNDLE_COMMENT = "<!-- END MEMBUNDLE AGENT MEMORY -->"

# Six skill documents under .agents/skills/membundle-memory/.
SKILL_FILENAMES = (
    "SKILL.md",
    "discovery.md",
    "remember.md",
    "update.md",
    "relationships.md",
    "examples.md",
)

# Success-report identities for the four bootstrap components.
COMPONENT_KNOWLEDGE = "knowledge"
COMPONENT_SKILL = "membundle-memory"
COMPONENT_AGENTS = "AGENTS.md"
COMPONENT_MAKEFILE = "Makefile"
ALL_COMPONENTS = (
    COMPONENT_KNOWLEDGE,
    COMPONENT_SKILL,
    COMPONENT_AGENTS,
    COMPONENT_MAKEFILE,
)

_MARKDOWN_LIST_ITEM = re.compile(r"^[ \t]*(?:[*+\-]|\d+[.)])[ \t]+(.*)$")
_ISO_DATE_HEADING = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ATX_HEADING = re.compile(r"^(#{1,6})(?:[ \t]+(.+?))?[ \t]*#*[ \t]*$")
_SETEXT_UNDERLINE = re.compile(r"^(?:=+|-+)[ \t]*$")
_MAKE_ASSIGN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*[+:?]?=\s*(.*)$"
)
_MAKE_TARGET = re.compile(r"^(\S[^:=]*?)\s*:(?!=)\s*(.*)$")

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None


def _workdir_has_product_sources(root: Path) -> bool:
    """True when *root* is a product tree: a Go module (``go.mod``) with a root
    ``Makefile`` (Contract "Build": ``make build`` at the root writes
    ``bin/membundle``). The Makefile's text is not read."""
    return (root / "Makefile").is_file() and (root / "go.mod").is_file()


def _run_product_build(root: Path) -> None:
    """Run ``GOFLAGS=-buildvcs=false make build`` in a writable copy of the judge workdir.

    Uses the Go toolchain and module cache already in the environment.
    A build that does not produce the binary is not a substrate exception;
    callers then observe the missing bootstrap results.
    """
    env = dict(os.environ)
    env["GOFLAGS"] = "-buildvcs=false"
    print(f"[F02] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F02] make build could not start: {exc}", flush=True)
        return
    print(f"[F02] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        print(
            f"[F02] make build stdout={completed.stdout[-2000:]!r} "
            f"stderr={completed.stderr[-2000:]!r}",
            flush=True,
        )


def _workdir_membundle() -> Path | None:
    """Return the ``bin/membundle`` built from the judge workdir sources.

    The judge workdir is the pytest process cwd. Its sources are built in a
    writable copy (``stage_writable_sources``). Does not search ``PATH``,
    does not honor ``PRODUCT_BIN``, and does not use a binary this build did
    not just produce. An empty workdir therefore has no executable. The
    build runs once per process when the workdir contains the product sources.
    """
    global _BUILD_DONE, _BUILT_BIN
    with _BUILD_LOCK:
        if not _BUILD_DONE:
            root = Path.cwd().resolve()
            candidate: Path | None = None
            if _workdir_has_product_sources(root):
                stage = stage_writable_sources(root)
                _run_product_build(stage)
                candidate = (stage / _BIN_REL).resolve()
            if (
                candidate is not None
                and candidate.is_file()
                and os.access(candidate, os.X_OK)
            ):
                _BUILT_BIN = candidate
            else:
                _BUILT_BIN = None
            _BUILD_DONE = True
            print(f"[F02] resolved workdir binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def _bootstrap_without_executable(
    ws: Workspace,
    args: Sequence[str],
    cwd: str | Path | None,
) -> RunResult:
    """Non-success bootstrap outcome with no report and no files written.

    Existing bootstrap-result assertions fail on this outcome because the
    target components were not written and the process did not report the
    components that were not skipped.
    """
    if cwd is not None:
        workdir = str(Path(cwd).resolve())
    else:
        workdir = str(ws.path)
    return RunResult(
        returncode=1,
        stdout=b"",
        stderr=b"",
        argv=("membundle", *args),
        cwd=workdir,
    )


def run_bootstrap(
    ws: Workspace,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle bootstrap`` with optional target and caller options.

    Builds ``bin/membundle`` from a writable copy of the judge workdir when it contains
    the product sources, then runs only that binary. When it is still absent,
    returns a failed bootstrap result instead of raising ``FileNotFoundError``.
    """
    args = ["bootstrap", *[str(a) for a in extra_args]]
    print(f"[F02] bootstrap extra_args={list(extra_args)!r} cwd={cwd!r}", flush=True)
    binary = _workdir_membundle()
    if binary is None:
        # TEST-FIX(F02): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
        return _bootstrap_without_executable(ws, args, cwd)
    try:
        return ws.invoke(args, env_updates=env_updates, cwd=cwd, binary=binary)
    except FileNotFoundError:
        # TEST-FIX(F02): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
        if binary.is_file() and os.access(binary, os.X_OK):
            raise
        return _bootstrap_without_executable(ws, args, cwd)


def run_bootstrap_with_dates(
    ws: Workspace,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> tuple[RunResult, frozenset[str]]:
    """Run bootstrap and capture the host UTC dates spanning the invoke."""
    before = utc_today_iso()
    result = run_bootstrap(
        ws, extra_args=extra_args, env_updates=env_updates, cwd=cwd
    )
    after = utc_today_iso()
    return result, utc_dates_spanning_invoke(before, after)


# Contract Output forms, ``bootstrap``: component token printed after
# two spaces and ``- `` on each component line, in the stated order.
COMPONENT_TOKENS = {
    COMPONENT_KNOWLEDGE: "knowledge/",
    COMPONENT_SKILL: ".agents/skills/membundle-memory/",
    COMPONENT_AGENTS: "AGENTS.md",
    COMPONENT_MAKEFILE: "Makefile",
}
BOOTSTRAP_CREATED_LINE = "Created:"
_COMPONENT_LINE_PREFIX = "  - "


def bootstrap_named_path(result: RunResult) -> str:
    """The project path this test passed to ``bootstrap`` (``.`` when omitted).

    Read from the test's own argument vector, not from product output.
    """
    args = list(result.argv[2:])
    if args and not args[0].startswith("-"):
        return args[0]
    return "."


def bootstrap_report_components(report: str, path: str) -> list[str]:
    """Component identities listed by a ``bootstrap`` success report, in order.

    Contract Output forms, ``bootstrap``: a first line that contains
    ``'<path>'`` (other wording free), then
    ``Created:``, then one line per not-skipped component: two spaces,
    ``- ``, then the component token (rest of the line free). Later lines
    never begin with two spaces and ``- ``. Raises ``AssertionError`` when
    the report does not have that form.
    """
    lines = report.split("\n")
    first = f"'{path}'"
    if len(lines) < 2 or first not in lines[0] or lines[1] != BOOTSTRAP_CREATED_LINE:
        raise AssertionError(
            f"bootstrap success report does not begin with a line containing "
            f"{first!r} and a {BOOTSTRAP_CREATED_LINE!r} line: {report!r}"
        )
    found: list[str] = []
    index = 2
    while index < len(lines) and lines[index].startswith(_COMPONENT_LINE_PREFIX):
        rest = lines[index][len(_COMPONENT_LINE_PREFIX):]
        matched = [
            component
            for component, token in COMPONENT_TOKENS.items()
            if rest.startswith(token)
        ]
        if len(matched) != 1:
            raise AssertionError(
                f"component line {lines[index]!r} does not begin with one of "
                f"the component tokens {list(COMPONENT_TOKENS.values())!r}"
            )
        found.append(matched[0])
        index += 1
    trailing = [
        line for line in lines[index:] if line.startswith(_COMPONENT_LINE_PREFIX)
    ]
    if trailing:
        raise AssertionError(
            f"bootstrap success report has component-shaped lines after the "
            f"component list: {trailing!r}"
        )
    print(f"[F02] report component lines={found!r}", flush=True)
    return found


def report_names_component(report: str, component: str, path: str = ".") -> bool:
    """True when the report's ``Created:`` list has a line for *component*."""
    return component in bootstrap_report_components(report, path)


def require_bootstrap_success(
    result: RunResult,
    expected_components: Sequence[str],
) -> str:
    """Success carrier: status 0 and the stated report listing exactly the not-skipped set.

    The component lines must be exactly *expected_components* in the stated
    order (knowledge, skill, ``AGENTS.md``, ``Makefile``); a skipped component
    has no line. Standard error is empty. Returns standard output.
    """
    report = result.stdout_text
    stderr = result.stderr_text
    print(
        f"[F02] success-carrier exit={result.returncode} stdout={report!r} "
        f"stderr={stderr!r}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"bootstrap did not end successfully (exit {result.returncode}); "
            f"stdout={report!r} stderr={stderr!r}"
        )
    if stderr:
        raise AssertionError(
            f"bootstrap success wrote on standard error: {stderr!r}"
        )
    listed = bootstrap_report_components(report, bootstrap_named_path(result))
    expected = [c for c in ALL_COMPONENTS if c in set(expected_components)]
    if listed != expected:
        raise AssertionError(
            "bootstrap success report component lines are not exactly the "
            f"not-skipped components {expected!r} in order; listed {listed!r}; "
            f"report={report!r}"
        )
    return report


def require_bootstrap_failure(result: RunResult) -> RunResult:
    """Failure carrier: non-success status. Streams are not required."""
    report = combined_report(result)
    print(
        f"[F02] failure-carrier exit={result.returncode} report={report!r}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            "bootstrap succeeded on an uncreatable target; "
            f"report={report!r}"
        )
    return result


def extract_membundle_agents_block(agents_text: str) -> str:
    """Text after the first BEGIN comment until the first END comment.

    Raises ``HarnessError`` if either delimiter is missing or END is not
    after BEGIN. Does not require the comments to be the first or last
    lines of the file.
    """
    begin_at = agents_text.find(BEGIN_MEMBUNDLE_COMMENT)
    if begin_at < 0:
        end_at = agents_text.find(END_MEMBUNDLE_COMMENT)
        if end_at >= 0:
            raise HarnessError(
                "END delimiter is present but BEGIN is missing or END is "
                "not after BEGIN"
            )
        raise HarnessError("BEGIN delimiter comment is missing")
    after_begin = begin_at + len(BEGIN_MEMBUNDLE_COMMENT)
    end_at = agents_text.find(END_MEMBUNDLE_COMMENT, after_begin)
    if end_at < 0:
        raise HarnessError(
            "END delimiter comment is missing or is not after BEGIN"
        )
    return agents_text[after_begin:end_at]


def assert_delimited_block_nonempty(block: str) -> None:
    """Raise if the extracted delimited block is empty after strip."""
    if not block.strip():
        raise AssertionError("delimited MEMBUNDLE Agent Memory block is empty")


_MD_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_FENCE_LINE = re.compile(r"^```.*$", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_BACKTICK = re.compile(r"`+")
# An intraword underscore is not emphasis (CommonMark), so tool names such as
# membundle_validate keep their underscore and stay matchable.
_MD_EMPHASIS = re.compile(r"[*~]{1,3}|(?<![A-Za-z0-9])_{1,3}|_{1,3}(?![A-Za-z0-9])")
_MD_HEADING = re.compile(r"^#{1,6}[ \t]*", re.MULTILINE)
_MD_QUOTE = re.compile(r"^[ \t]*>+[ \t]?", re.MULTILINE)
_MD_LIST = re.compile(r"^[ \t]*(?:[*+\-]|\d+[.)])[ \t]+", re.MULTILINE)


def _strip_markdown_markers(block: str) -> str:
    """Drop Markdown decoration; keep the prose those markers wrap.

    Headings, list markers, quotes, emphasis, backticks, and link
    punctuation are removed so a duty stated as a paragraph is still
    locatable. Does not count leftover units.
    """
    text = _MD_HTML_COMMENT.sub(" ", block)
    text = _MD_FENCE_LINE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_BACKTICK.sub("", text)
    text = _MD_EMPHASIS.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_LIST.sub("", text)
    return text


# Each named duty is recognised by the effect it describes, not by this
# checkout's sentences: a family of stems for the action and one for the
# qualifier that makes it that duty. A block that states the duty as
# "look up prior memory before writing" or as "membundle_search before proposing"
# is the same duty; a block of filler names neither half.
_SEARCH_ACTION = re.compile(
    r"(?i)\b(?:search\w*|look\s*-?\s*up|lookup|consult\w*|retriev\w*|"
    r"quer(?:y|ies)\w*|find|check\s+(?:for\s+)?existing|membundle_search)"
)
_BEFORE_WRITE = re.compile(
    r"(?i)\b(?:before|prior|first|ahead\s+of|existing|already)\b"
)
_GUARD_CLAUSE = re.compile(
    r"(?i)\b(?:governance|guard\w*|gate\w*|polic(?:y|ies)|frozen|"
    r"stop|halt|refuse\w*|forbid\w*|never|must\s+not|do\s+not)\b"
)
_VALIDATE_ACTION = re.compile(
    r"(?i)\b(?:validat\w*|verif\w*|check\w*|lint\w*|assert\w*|membundle_validate)"
)
_BEFORE_EXIT = re.compile(
    r"(?i)\b(?:exit\w*|finish\w*|complet\w*|done|end(?:ing)?|final\w*|"
    r"pipeline|before)\b"
)


def _block_has_search_before_write(stripped: str) -> bool:
    """A search / look-up step ordered before writing, in any wording."""
    return (
        _SEARCH_ACTION.search(stripped) is not None
        and _BEFORE_WRITE.search(stripped) is not None
    )


def _block_has_governance_guard(stripped: str) -> bool:
    """A guard clause: something governs, gates, holds, or stops an action."""
    return _GUARD_CLAUSE.search(stripped) is not None


def _block_has_validation_before_exit(stripped: str) -> bool:
    """A validation / verification step tied to finishing."""
    return (
        _VALIDATE_ACTION.search(stripped) is not None
        and _BEFORE_EXIT.search(stripped) is not None
    )


def assert_delimited_block_contents(block: str) -> None:
    """extracted inner holds the three named duties.

    After Markdown markers are stripped, a search-before-write invariant,
    a governance guard clause, and a completion pipeline that requires
    validation before exit are each independently locatable. A filler
    inner that only has delimiters fails; a block that states all three
    duties as paragraphs passes. Does not count headings, list items,
    quotes, or leftover lines, and does not require this checkout's
    sentences, tool names, RFC 2119 modals, governance-tier literals,
    or the specification stems used to name the roles (search, governance,
    validat) as required tokens. Each duty is identified by that role:
    a look-up of existing memory prior to writing, a guard that stops an
    edit, and verify-before-exit pass, as does this checkout's template.
    A role-free inner fails.
    """
    assert_delimited_block_nonempty(block)
    stripped = _strip_markdown_markers(block)
    has_search = _block_has_search_before_write(stripped)
    has_gov = _block_has_governance_guard(stripped)
    has_pipeline = _block_has_validation_before_exit(stripped)
    print(
        f"[F02] block duties search_before_write={has_search} "
        f"governance={has_gov} validation_before_exit={has_pipeline} "
        f"stripped_len={len(stripped)}",
        flush=True,
    )
    missing: list[str] = []
    if not has_search:
        missing.append("search-before-write invariant")
    if not has_gov:
        missing.append("governance guard clause")
    if not has_pipeline:
        missing.append(
            "completion pipeline that requires validation before exit"
        )
    if missing:
        raise AssertionError(
            "delimited MEMBUNDLE Agent Memory inner does not independently "
            "locate each named duty after Markdown markers are stripped: "
            f"missing {missing!r}; stripped={stripped!r}"
        )


def assert_agents_file_missing_write(path: str | Path, project_name: str) -> None:
    """Missing-file / overwrite write: delimiters, name, block contents."""
    agents_path = Path(path)
    if not path_is_file(agents_path):
        raise AssertionError(f"missing AGENTS.md at {agents_path}")
    text = read_file(agents_path)
    print(
        f"[F02] AGENTS.md {agents_path} bytes={len(text)} "
        f"name_present={project_name in text}",
        flush=True,
    )
    if project_name not in text:
        raise AssertionError(
            f"AGENTS.md does not contain the project name {project_name!r}"
        )
    block = extract_membundle_agents_block(text)
    assert_delimited_block_contents(block)


def dated_section_has_list_item(section: str) -> bool:
    """True when *section* contains a Markdown list item with item text."""
    for line in section.splitlines():
        match = _MARKDOWN_LIST_ITEM.match(line)
        if match is None:
            continue
        if match.group(1).strip():
            return True
    return False


def markdown_heading_sections(markdown: str) -> list[tuple[str, str]]:
    """Each heading's text and the body until the next heading.

    ATX and Setext headings both count. A title heading before a date
    heading does not hide the later section. An empty heading list is a
    real observation of a file with no heading, not a failed read.
    """
    lines = markdown.splitlines()
    found: list[tuple[int, int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        atx = _ATX_HEADING.match(line)
        if atx is not None and line.lstrip().startswith("#"):
            text = (atx.group(2) or "").strip()
            if text:
                found.append((index + 1, index, text))
                index += 1
                continue
        if index + 1 < len(lines) and _SETEXT_UNDERLINE.match(lines[index + 1]):
            text = line.strip()
            if text and not line.lstrip().startswith("#"):
                found.append((index + 2, index, text))
                index += 2
                continue
        index += 1
    sections: list[tuple[str, str]] = []
    for pos, (content_start, _marker, text) in enumerate(found):
        if pos + 1 < len(found):
            next_marker = found[pos + 1][1]
            body = "\n".join(lines[content_start:next_marker])
        else:
            body = "\n".join(lines[content_start:])
        sections.append((text, body))
    return sections


def _utc_dated_section(
    markdown: str,
    allowed_dates: frozenset[str],
) -> tuple[str, str]:
    """Heading whose text is an allowed UTC date, and the section under it.

    The date heading may sit anywhere. Raises ``AssertionError`` when no
    such heading exists — that is a missed carrier, not an unreadable file.
    """
    sections = markdown_heading_sections(markdown)
    headings = [text for text, _body in sections]
    print(
        f"[F02] log headings={headings!r} allowed={sorted(allowed_dates)}",
        flush=True,
    )
    for text, body in sections:
        if _ISO_DATE_HEADING.fullmatch(text) and text in allowed_dates:
            return text, body
    raise AssertionError(
        "log has no heading whose text is today's UTC date in YYYY-MM-DD "
        f"form among {sorted(allowed_dates)}; headings={headings!r}"
    )


def utc_date_heading_text(
    markdown: str,
    allowed_dates: frozenset[str],
) -> str:
    """Text of a heading that is an allowed UTC ``YYYY-MM-DD``, wherever it sits."""
    heading, _body = _utc_dated_section(markdown, allowed_dates)
    return heading


def section_under_utc_date_heading(
    markdown: str,
    allowed_dates: frozenset[str],
) -> str:
    """Body under a heading whose text is an allowed UTC date."""
    _heading, body = _utc_dated_section(markdown, allowed_dates)
    return body


def assert_bootstrap_log(
    log_path: str | Path,
    allowed_dates: frozenset[str] | None = None,
) -> None:
    """UTC ISO date heading plus a list item under that section.

    The date heading is not required to be the first heading in the file.
    """
    dates = (
        allowed_dates
        if allowed_dates is not None
        else frozenset({utc_today_iso()})
    )
    text = read_file(log_path)
    heading, section = _utc_dated_section(text, dates)
    print(
        f"[F02] log {log_path} utc_date_heading={heading!r} "
        f"section={section!r}",
        flush=True,
    )
    if not dated_section_has_list_item(section):
        raise AssertionError(
            "dated heading section has no Markdown list item under "
            f"{heading!r}"
        )


def assert_knowledge_scaffold(
    project_dir: str | Path,
    allowed_dates: frozenset[str],
    project_name: str | None = None,
) -> None:
    """knowledge/index.md + knowledge/log.md A-quality observations."""
    root = Path(project_dir)
    knowledge = root / "knowledge"
    index_path = knowledge / "index.md"
    log_path = knowledge / "log.md"
    if not path_is_file(index_path):
        raise AssertionError(f"missing knowledge/index.md under {root}")
    if not path_is_file(log_path):
        raise AssertionError(f"missing knowledge/log.md under {root}")
    assert_index_structure(index_path)
    if project_name is not None:
        _mapping, body = split_yaml_frontmatter(read_file(index_path))
        heading = first_heading_text(body)
        print(
            f"[F02] index heading={heading!r} project_name={project_name!r}",
            flush=True,
        )
        if project_name not in heading:
            raise AssertionError(
                f"index heading {heading!r} does not contain the project "
                f"name {project_name!r}"
            )
    assert_bootstrap_log(log_path, allowed_dates=allowed_dates)


def assert_skill_tree(project_dir: str | Path) -> None:
    """All six named skill files exist and each is a non-empty file."""
    skill_dir = Path(project_dir) / ".agents" / "skills" / "membundle-memory"
    if not path_is_dir(skill_dir):
        raise AssertionError(
            f"missing skill directory .agents/skills/membundle-memory/ under "
            f"{project_dir}"
        )
    for name in SKILL_FILENAMES:
        path = skill_dir / name
        if not path_is_file(path):
            raise AssertionError(f"missing skill file: {path}")
        content = read_file(path)
        print(f"[F02] skill {name} bytes={len(content)}", flush=True)
        if len(content) == 0:
            raise AssertionError(f"skill file is empty: {path}")


def _is_recipe_continuation(line: str) -> bool:
    """True when *line* continues a target with an indented command.

    Make recipes are often tab-indented; a space-indented command is still
    a recipe line. Does not require tab syntax as the PRD never named it.
    """
    if not line or line[0] not in " \t":
        return False
    if _MAKE_ASSIGN.match(line.lstrip()) is not None:
        return False
    if _MAKE_TARGET.match(line.lstrip()) is not None:
        return False
    return True


def assert_makefile_has_recipes(makefile_path: str | Path) -> None:
    """At least one command-bearing recipe line."""
    path = Path(makefile_path)
    if not path_is_file(path):
        raise AssertionError(f"missing Makefile at {path}")
    text = read_file(path)
    print(f"[F02] Makefile {path} bytes={len(text)}", flush=True)
    for line in text.splitlines():
        if not _is_recipe_continuation(line):
            continue
        body = line.strip()
        if body and not body.startswith("#"):
            return
    raise AssertionError(
        f"Makefile has no command-bearing recipe line (comment-only or empty): "
        f"{path}"
    )


def _command_bearing_recipe_bodies(text: str) -> list[str]:
    """Command bodies of recipe lines (indent may be tab or space)."""
    bodies: list[str] = []
    in_target = False
    for line in text.splitlines():
        if _is_recipe_continuation(line):
            if in_target:
                body = line.strip()
                if body and not body.startswith("#"):
                    bodies.append(body)
            continue
        in_target = False
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _MAKE_ASSIGN.match(line) is not None:
            continue
        if _MAKE_TARGET.match(line) is not None:
            in_target = True
    return bodies


def _assignment_values(text: str) -> list[str]:
    """Right-hand sides of Make assignments (variable factoring)."""
    values: list[str] = []
    for line in text.splitlines():
        match = _MAKE_ASSIGN.match(line)
        if match is not None:
            values.append(match.group(2).strip())
    return values


def _recipe_is_echo(body: str) -> bool:
    """True when *body* only prints (does not run a convenience duty)."""
    command = body.lstrip("@+- \t")
    if not command:
        return False
    first = command.split(None, 1)[0]
    return first in {"echo", "printf"}


def _makefile_duty_observable(text: str) -> str:
    """Recipe commands plus assignment values; echo/printf lines dropped.

    A recipe that only echoes does not carry a duty. Assignments are
    included so a bundle path or flags may live in a Make variable.
    Does not include target names or this checkout's binary path.
    """
    parts: list[str] = []
    for body in _command_bearing_recipe_bodies(text):
        if _recipe_is_echo(body):
            continue
        parts.append(body)
    parts.extend(_assignment_values(text))
    return "\n".join(parts).casefold()


def _recipes_have_strict_and_drift_validation(observable: str) -> bool:
    """Named duty: strict-and-drift validation on knowledge/."""
    return (
        "validat" in observable
        and "strict" in observable
        and "drift" in observable
        and "knowledge" in observable
    )


def _recipes_have_search_of_bundle(observable: str) -> bool:
    """Named duty: search of that knowledge/ bundle."""
    return "search" in observable and "knowledge" in observable


def assert_makefile_convenience_tasks(makefile_path: str | Path) -> None:
    """written Makefile recipes include both named convenience duties.

    Command-bearing recipes must include strict-and-drift validation on
    knowledge/ and search of that bundle. The two duties may share one
    target or use more than two. Does not require a target count, target
    names, tab characters, or this checkout's binary path. A recipe that
    only echoes fails. Does not execute ``make``.
    """
    assert_makefile_has_recipes(makefile_path)
    text = read_file(makefile_path)
    observable = _makefile_duty_observable(text)
    has_validate = _recipes_have_strict_and_drift_validation(observable)
    has_search = _recipes_have_search_of_bundle(observable)
    print(
        f"[F02] makefile duties strict_drift_validation={has_validate} "
        f"search_bundle={has_search} observable={observable!r}",
        flush=True,
    )
    missing: list[str] = []
    if not has_validate:
        missing.append("strict-and-drift validation on knowledge/")
    if not has_search:
        missing.append("search of that bundle")
    if missing:
        raise AssertionError(
            "Makefile command-bearing recipes do not include both named "
            f"convenience duties: missing {missing!r}; "
            f"path={makefile_path}; observable={observable!r}"
        )


def assert_full_bootstrap_quality(
    project_dir: str | Path,
    allowed_dates: frozenset[str],
    project_name: str,
    result: RunResult,
) -> None:
    """A-quality four components plus the four-name success carrier."""
    require_bootstrap_success(result, ALL_COMPONENTS)
    root = Path(project_dir)
    if not path_is_dir(root):
        raise AssertionError(f"bootstrap target directory does not exist: {root}")
    assert_knowledge_scaffold(root, allowed_dates, project_name=project_name)
    assert_skill_tree(root)
    assert_agents_file_missing_write(root / "AGENTS.md", project_name)
    assert_makefile_convenience_tasks(root / "Makefile")


def run_agents_md_detection_contrast(
    ws: Workspace,
    *,
    detect_rel: str,
    baseline_rel: str,
    detect_body: str,
    baseline_body: str,
) -> tuple[bytes, bytes, str]:
    """Two overwrite-off bootstraps that differ only in the starting AGENTS.md.

    *detect_body* and *baseline_body* must differ only by omitting the
    detection string under test. Returns ``(before_detect, after_detect,
    baseline_text)``.
    """
    detect_dir = ws.resolve(detect_rel)
    baseline_dir = ws.resolve(baseline_rel)
    detect_dir.mkdir()
    baseline_dir.mkdir()
    detect_path = detect_dir / "AGENTS.md"
    baseline_path = baseline_dir / "AGENTS.md"
    detect_path.write_text(detect_body, encoding="utf-8")
    baseline_path.write_text(baseline_body, encoding="utf-8")
    before = read_bytes(detect_path)
    detect_result, _dates_d = run_bootstrap_with_dates(
        ws, extra_args=(detect_rel,)
    )
    baseline_result, _dates_b = run_bootstrap_with_dates(
        ws, extra_args=(baseline_rel,)
    )
    require_bootstrap_success(detect_result, ALL_COMPONENTS)
    require_bootstrap_success(baseline_result, ALL_COMPONENTS)
    after = read_bytes(detect_path)
    baseline_text = read_file(baseline_path)
    print(
        f"[F02] detection contrast detect_unchanged={after == before} "
        f"baseline_bytes={len(baseline_text)}",
        flush=True,
    )
    return before, after, baseline_text


def assert_skip_makefile_report_not_installed(
    full_report: str,
    skip_report: str,
    path_tokens: Sequence[str],
    full_path: str | None = None,
    skip_path: str | None = None,
) -> None:
    """the full run lists ``Makefile`` as created; the skip run does not.

    Reads the ``Created:`` component lines of each report (Contract Output
    forms, ``bootstrap``). *path_tokens* is accepted for call compatibility;
    *full_path* / *skip_path* are the project paths the runs named (taken
    from the first entry of *path_tokens* order ``(skip, full, ...)`` when
    omitted).
    """
    tokens = [str(tok) for tok in path_tokens if tok]
    if skip_path is None:
        skip_path = tokens[0]
    if full_path is None:
        full_path = tokens[1]
    full_listed = bootstrap_report_components(full_report, full_path)
    skip_listed = bootstrap_report_components(skip_report, skip_path)
    full_installed = COMPONENT_MAKEFILE in full_listed
    skip_installed = COMPONENT_MAKEFILE in skip_listed
    print(
        f"[F02] skip-Makefile full_installed={full_installed} "
        f"skip_installed={skip_installed}",
        flush=True,
    )
    if not full_installed:
        raise AssertionError(
            "full-run success report has no Makefile component line; "
            f"report={full_report!r}"
        )
    if skip_installed:
        raise AssertionError(
            "skip-Makefile success report still has a Makefile component "
            f"line; report={skip_report!r}"
        )
