#!/usr/bin/env python3
"""Parse per-test pass/total counts from a test runner's stdout/stderr.

The final judge runs one fixed ``test_command`` and currently scores a binary
reward from the exit code only. This module adds a *fine-grained* pass rate
(e.g. ``89/89`` or ``50/100``) by parsing the framework's own summary line, so
the leaderboard can show ``passed_count/total_count`` alongside the binary
``passed``.

Contract (deliberately conservative, per plan §A):

- ``parse_test_counts(output, framework_label=..., test_command=...) -> Counts | None``
- Returns ``None`` when the framework cannot be identified *or* its summary
  cannot be parsed. The caller then records ``passed_count/total_count = null``
  and falls back to the exit code for ``passed`` — never a guessed number.
- ``total`` counts executed, non-skipped tests (passed + failed + errors).
  ``passed`` is the framework's reported pass count. ``pass_rate`` is
  ``passed / total`` (``None`` when ``total == 0``).

No per-case hard-coding: routing is by ``framework_label`` / ``test_command``
keywords, with a generic fallback that tries every parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Counts:
    passed: int
    failed: int
    errors: int
    skipped: int
    framework: str

    @property
    def total(self) -> int:
        """Executed, non-skipped tests."""
        return self.passed + self.failed + self.errors

    @property
    def pass_rate(self) -> float | None:
        t = self.total
        return (self.passed / t) if t else None

    def as_dict(self) -> dict:
        return {
            "framework": self.framework,
            "passed_count": self.passed,
            "failed_count": self.failed,
            "error_count": self.errors,
            "skipped_count": self.skipped,
            "total_count": self.total,
            "pass_rate": self.pass_rate,
        }


# --- individual framework parsers ------------------------------------------
# Each returns (passed, failed, errors, skipped) or None. ``total`` is derived.


# Bound work on assertion reprs before matching the summary grammar. Both
# normal and quiet pytest output use the same count/duration body; separator
# lines and terminal colors are presentation only.
_MAX_SUMMARY_LINE = 4000
_PYTEST_COUNT = r"\d+\s+(?:passed|failed|errors?|skipped|deselected|xfailed|xpassed|warnings?|rerun)"
_PYTEST_SUMMARY = re.compile(
    rf"(?P<counts>{_PYTEST_COUNT}(?:,\s+{_PYTEST_COUNT})*)"
    r"\s+in\s+\d+(?:\.\d+)?s(?:\s+\(\d+:\d{2}(?::\d{2})?\))?"
)
_ANSI_SGR = re.compile(r"\x1b\[[\d;]*m")


def _parse_pytest(out: str) -> tuple[int, int, int, int] | None:
    # Final summary line, e.g.
    #   ===== 1 failed, 88 passed, 2 skipped, 1 error in 5.00s =====
    #   ===== 89 passed in 3.40s =====
    #   ===== 243 failed, 264 passed in 98.33s (0:01:38) =====
    #   89 passed, 1 warning in 3.40s
    summary = None
    for line in out.splitlines():
        if len(line) > _MAX_SUMMARY_LINE:
            continue
        stripped = _ANSI_SGR.sub("", line).strip()
        if stripped.startswith("=") and stripped.endswith("="):
            stripped = stripped.strip("=").strip()
        match = _PYTEST_SUMMARY.fullmatch(stripped)
        if match is not None:
            summary = match.group("counts")
    if summary is None:
        return None

    def grab(*words: str) -> int:
        total = 0
        for w in words:
            m = re.search(rf"(\d+)\s+{w}\b", summary)
            if m:
                total += int(m.group(1))
        return total

    passed = grab("passed")
    failed = grab("failed")
    errors = grab("error", "errors")
    skipped = grab("skipped", "deselected")
    if passed == failed == errors == 0:
        return None
    return passed, failed, errors, skipped


def _parse_cargo(out: str) -> tuple[int, int, int, int] | None:
    # One ``test result:`` line per test binary / doctest; sum them.
    matches = re.findall(
        r"test result:\s+\w+\.\s+(\d+)\s+passed;\s+(\d+)\s+failed;\s+(\d+)\s+ignored",
        out,
    )
    if not matches:
        return None
    passed = sum(int(p) for p, _f, _i in matches)
    failed = sum(int(f) for _p, f, _i in matches)
    skipped = sum(int(i) for _p, _f, i in matches)
    return passed, failed, 0, skipped


def _parse_dotnet(out: str) -> tuple[int, int, int, int] | None:
    # ``Passed!  - Failed: 0, Passed: 89, Skipped: 0, Total: 89, Duration: ...``
    # (one block per test project; sum them). Also matches ``Failed! - ...``.
    blocks = re.findall(
        r"(?:Passed!|Failed!|Skipped!)\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+)",
        out,
    )
    if not blocks:
        return None
    failed = sum(int(f) for f, _p, _s in blocks)
    passed = sum(int(p) for _f, p, _s in blocks)
    skipped = sum(int(s) for _f, _p, s in blocks)
    return passed, failed, 0, skipped


def _parse_flutter(out: str) -> tuple[int, int, int, int] | None:
    # Timestamped status lines: ``00:05 +89: All tests passed!`` or
    # ``00:05 +87 -2: Some tests failed.``. Take the last one.
    last = None
    for m in re.finditer(r"\+(\d+)(?:\s+-(\d+))?\s*:", out):
        last = m
    if last is None:
        return None
    passed = int(last.group(1))
    failed = int(last.group(2) or 0)
    return passed, failed, 0, 0


def _parse_vitest(out: str) -> tuple[int, int, int, int] | None:
    # ``Tests  2 failed | 87 passed (89)`` / ``Tests  89 passed (89)``
    m = re.search(r"Tests\s+(.+?)\((\d+)\)", out)
    if not m:
        return None
    body, total = m.group(1), int(m.group(2))
    passed = int(p.group(1)) if (p := re.search(r"(\d+)\s+passed", body)) else 0
    failed = int(f.group(1)) if (f := re.search(r"(\d+)\s+failed", body)) else 0
    skipped = int(s.group(1)) if (s := re.search(r"(\d+)\s+skipped", body)) else 0
    if passed == failed == 0:
        return None
    return passed, failed, 0, max(skipped, total - passed - failed)


def _parse_jest(out: str) -> tuple[int, int, int, int] | None:
    # ``Tests:       2 failed, 87 passed, 89 total``
    m = re.search(r"Tests:\s+(.+?,\s*\d+\s+total)", out)
    if not m:
        return None
    body = m.group(1)
    passed = int(p.group(1)) if (p := re.search(r"(\d+)\s+passed", body)) else 0
    failed = int(f.group(1)) if (f := re.search(r"(\d+)\s+failed", body)) else 0
    skipped = int(s.group(1)) if (s := re.search(r"(\d+)\s+(?:skipped|todo)", body)) else 0
    if passed == failed == 0:
        return None
    return passed, failed, 0, skipped


def _parse_mocha(out: str) -> tuple[int, int, int, int] | None:
    pm = re.search(r"(\d+)\s+passing", out)
    if pm is None:
        return None
    passed = int(pm.group(1))
    failed = int(f.group(1)) if (f := re.search(r"(\d+)\s+failing", out)) else 0
    skipped = int(s.group(1)) if (s := re.search(r"(\d+)\s+pending", out)) else 0
    return passed, failed, 0, skipped


def _parse_tap(out: str) -> tuple[int, int, int, int] | None:
    # Raw TAP stream: ``ok N`` / ``not ok N`` lines, plan ``1..N``.
    ok = len(re.findall(r"(?m)^ok\s+\d+", out))
    notok = len(re.findall(r"(?m)^not ok\s+\d+", out))
    if ok == 0 and notok == 0:
        return None
    skipped = len(re.findall(r"(?mi)^ok\s+\d+.*#\s*skip", out))
    return ok - skipped, notok, 0, skipped


def _parse_prove(out: str) -> tuple[int, int, int, int] | None:
    # perl ``prove`` summary: ``Files=1, Tests=89, ...`` (+ ``Result: PASS/FAIL``).
    tm = re.search(r"\bTests=(\d+)", out)
    if tm is None:
        return None
    total = int(tm.group(1))
    failed = 0
    fm = re.search(r"Failed\s+(\d+)/(\d+)\s+subtests", out)
    if fm:
        failed = int(fm.group(1))
    elif re.search(r"Result:\s*FAIL", out):
        failed = total  # FAIL without a parseable subtest count → treat all as failed
    return total - failed, failed, 0, 0


def _parse_ctest(out: str) -> tuple[int, int, int, int] | None:
    # ``100% tests passed, 0 tests failed out of 89``
    m = re.search(r"(\d+)\s+tests?\s+failed\s+out\s+of\s+(\d+)", out)
    if m is None:
        return None
    failed, total = int(m.group(1)), int(m.group(2))
    return total - failed, failed, 0, 0


def _parse_maven(out: str) -> tuple[int, int, int, int] | None:
    # surefire: last ``Tests run: 89, Failures: 0, Errors: 0, Skipped: 0``
    last = None
    for m in re.finditer(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)(?:,\s*Skipped:\s*(\d+))?",
        out,
    ):
        last = m
    if last is None:
        return None
    run = int(last.group(1))
    failed = int(last.group(2))
    errors = int(last.group(3))
    skipped = int(last.group(4) or 0)
    return run - failed - errors - skipped, failed, errors, skipped


def _parse_unittest(out: str) -> tuple[int, int, int, int] | None:
    # python unittest / nosetests: ``Ran 12 tests in 0.1s`` + ``OK`` /
    # ``FAILED (failures=2, errors=1, skipped=3)``.
    rm = re.search(r"Ran\s+(\d+)\s+tests?\s+in", out)
    if rm is None:
        return None
    ran = int(rm.group(1))
    failed = errors = skipped = 0
    fm = re.search(r"FAILED\s+\(([^)]*)\)", out)
    if fm:
        body = fm.group(1)
        failed = int(x.group(1)) if (x := re.search(r"failures=(\d+)", body)) else 0
        errors = int(x.group(1)) if (x := re.search(r"errors=(\d+)", body)) else 0
    sm = re.search(r"(?:OK|FAILED).*?skipped=(\d+)", out)
    if sm:
        skipped = int(sm.group(1))
    return ran - failed - errors - skipped, failed, errors, skipped


def _parse_go(out: str) -> tuple[int, int, int, int] | None:
    # Only resolvable with ``go test -v`` (``--- PASS:`` / ``--- FAIL:`` lines).
    passed = len(re.findall(r"(?m)^\s*--- PASS:", out))
    failed = len(re.findall(r"(?m)^\s*--- FAIL:", out))
    skipped = len(re.findall(r"(?m)^\s*--- SKIP:", out))
    if passed == 0 and failed == 0:
        return None
    return passed, failed, 0, skipped


def _parse_catch2(out: str) -> tuple[int, int, int, int] | None:
    # Catch2: ``test cases: 12 | 10 passed | 2 failed`` or
    # ``All tests passed (34 assertions in 5 test cases)``.
    m = re.search(r"test cases:\s*(\d+)\s*\|\s*(\d+)\s+passed(?:\s*\|\s*(\d+)\s+failed)?", out)
    if m:
        passed = int(m.group(2))
        failed = int(m.group(3) or 0)
        return passed, failed, 0, 0
    m = re.search(r"All tests passed\s+\(\d+\s+assertions?\s+in\s+(\d+)\s+test cases?\)", out)
    if m:
        cases = int(m.group(1))
        return cases, 0, 0, 0
    return None


_PARSERS = {
    "pytest": _parse_pytest,
    "cargo": _parse_cargo,
    "dotnet": _parse_dotnet,
    "flutter": _parse_flutter,
    "vitest": _parse_vitest,
    "jest": _parse_jest,
    "mocha": _parse_mocha,
    "tap": _parse_tap,
    "prove": _parse_prove,
    "ctest": _parse_ctest,
    "maven": _parse_maven,
    "unittest": _parse_unittest,
    "go": _parse_go,
    "catch2": _parse_catch2,
}

# Keyword -> parser key, checked against framework_label + test_command.
_ROUTES: tuple[tuple[str, str], ...] = (
    ("pytest", "pytest"),
    ("cargo", "cargo"),
    ("dotnet", "dotnet"),
    ("flutter", "flutter"),
    ("vitest", "vitest"),
    ("jest", "jest"),
    ("mocha", "mocha"),
    ("nosetest", "unittest"),
    ("unittest", "unittest"),
    ("prove", "prove"),
    ("ctest", "ctest"),
    ("catch2", "catch2"),
    ("catch", "catch2"),
    ("surefire", "maven"),
    ("maven", "maven"),
    ("mvn", "maven"),
    ("junit", "maven"),
    ("go test", "go"),
    ("tap", "tap"),
)

# Order used when no route matches (specific/unambiguous first).
_FALLBACK_ORDER = (
    "pytest", "cargo", "dotnet", "flutter", "vitest", "jest",
    "maven", "ctest", "catch2", "unittest", "mocha", "prove", "tap", "go",
)


def _route(framework_label: str, test_command: str) -> str | None:
    hay = f"{framework_label} {test_command}".lower()
    for kw, key in _ROUTES:
        if kw in hay:
            return key
    return None


_SHORT_SUMMARY = re.compile(r"^=+\s*short test summary info\s*=+$", re.I)
_OUTCOME_LINE = re.compile(r"^(FAILED|ERROR)\s+(\S+)")


def parse_pytest_outcomes(output: str) -> dict[str, list[str]] | None:
    """Names of failed / errored pytest items from the short summary.

    Returns None when the log is not a pytest short-summary. Collection
    errors appear as ``ERROR <path>``.
    """
    if not output:
        return None
    lines = output.splitlines()
    start = None
    for index, line in enumerate(lines):
        if _SHORT_SUMMARY.search(line.strip()):
            start = index + 1
    if start is None:
        return None
    failed: list[str] = []
    errors: list[str] = []
    seen_f: set[str] = set()
    seen_e: set[str] = set()
    for line in lines[start:]:
        if line.startswith("="):
            break
        match = _OUTCOME_LINE.match(line.strip())
        if match is None:
            continue
        kind, raw = match.group(1), match.group(2)
        name = raw.split(" - ", 1)[0].strip()
        if not name:
            continue
        if kind == "FAILED" and name not in seen_f:
            seen_f.add(name)
            failed.append(name)
        elif kind == "ERROR" and name not in seen_e:
            seen_e.add(name)
            errors.append(name)
    return {"failed": failed, "errors": errors}


def parse_test_counts(
    output: str,
    framework_label: str = "",
    test_command: str = "",
) -> Counts | None:
    """Best-effort pass/total extraction. Returns ``None`` if undeterminable."""
    if not output:
        return None

    key = _route(framework_label, test_command)
    if key is not None:
        res = _PARSERS[key](output)
        if res is not None:
            p, f, e, s = res
            return Counts(p, f, e, s, key)

    # Generic fallback: try every parser, accept the first confident hit.
    for fk in _FALLBACK_ORDER:
        if fk == key:
            continue
        res = _PARSERS[fk](output)
        if res is not None:
            p, f, e, s = res
            return Counts(p, f, e, s, fk)
    return None
