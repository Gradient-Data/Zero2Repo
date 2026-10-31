"""Declarative asset checks for a single case directory.

Callers pass any directory that looks like a case. The released suite is
not imported here so unit tests can use synthetic fixtures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from coding_bench_harbor._leakage import scan_leakage

from .denylist import ALLOWED_JUDGE_BANS, validate_denylist_artifact
from .substrates import KNOWN_PROVIDERS

__all__ = ["check_case_assets", "check_case_supply", "check_case_warnings", "main"]

_OUTSIDE_CACHE = "/opt/cb-cache"
_PRIVILEGE_MARKERS = (
    "mount(",
    "unshare",
    "losetup",
    "/dev/loop",
    "FICLONE",
    "CAP_SYS_ADMIN",
    "--privileged",
)


def check_case_assets(case_dir: Path | str) -> list[str]:
    """Return human-readable problems for *case_dir* (empty if clean)."""
    case_dir = Path(case_dir)
    errors: list[str] = []
    cid = case_dir.name

    manifest_path = case_dir / "source" / "manifest.json"
    lock_path = case_dir / "source" / "recipe.lock.json"
    prd_path = case_dir / "public" / "Full_PRD.md"
    contract_path = case_dir / "public" / "Interface_Contract.md"
    tests_manifest_path = case_dir / "milestones" / "final" / "test_manifest.json"
    final_dir = case_dir / "milestones" / "final"

    for path in (manifest_path, lock_path, prd_path, contract_path, tests_manifest_path):
        if not path.is_file():
            errors.append(f"{cid}: missing {path.relative_to(case_dir)}")

    manifest: dict = {}
    lock: dict = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: invalid manifest.json: {exc}")
            return errors
    if lock_path.is_file():
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: invalid recipe.lock.json: {exc}")
            return errors

    runner = manifest.get("runner") if isinstance(manifest.get("runner"), dict) else {}
    lock_runner = lock.get("runner") if isinstance(lock.get("runner"), dict) else {}
    for field in ("install_command", "build_command"):
        left = str(runner.get(field) or "")
        right = str(lock_runner.get(field) or "")
        if left != right:
            errors.append(f"{cid}: manifest and lock disagree on runner.{field}")

    install = str(runner.get("install_command") or "")
    resources = case_dir / "source" / "env" / "resources.json"
    if _OUTSIDE_CACHE in install and not resources.is_file():
        errors.append(
            f"{cid}: install_command references {_OUTSIDE_CACHE} without "
            "source/env/resources.json"
        )

    raw_bans = runner.get("judge_bans") or []
    if isinstance(raw_bans, str):
        raw_bans = [part.strip() for part in raw_bans.split(",")]
    for ban in raw_bans:
        token = str(ban).strip()
        if token and token not in ALLOWED_JUDGE_BANS:
            errors.append(f"{cid}: unknown judge_bans value {token!r}")

    terms = [str(t) for t in (manifest.get("sensitive_terms") or []) if str(t).strip()]
    public_text = ""
    if prd_path.is_file():
        public_text += prd_path.read_text(encoding="utf-8")
    if contract_path.is_file():
        public_text += "\n" + contract_path.read_text(encoding="utf-8")
    public_text += "\n" + str(runner.get("build_command") or "")
    for hit in scan_leakage(public_text, terms):
        errors.append(f"{cid}: public leakage of {hit.term!r} ({hit.occurrences})")

    denylist_path = case_dir / "source" / "denylist.json"
    if denylist_path.is_file():
        try:
            payload = json.loads(denylist_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: invalid denylist.json: {exc}")
        else:
            if isinstance(payload, dict) and isinstance(manifest, dict):
                errors.extend(validate_denylist_artifact(payload, manifest, case_id=cid))

    if tests_manifest_path.is_file():
        try:
            tests_manifest = json.loads(tests_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: invalid test_manifest.json: {exc}")
            return errors
        names = list(tests_manifest.get("test_files") or [])
        names.extend(tests_manifest.get("support_files") or [])
        for name in names:
            rel = Path(str(name))
            target = (final_dir / rel).resolve()
            try:
                target.relative_to(final_dir.resolve())
            except ValueError:
                errors.append(f"{cid}: test file escapes milestones/final: {name}")
                continue
            if not target.is_file() and not target.is_dir():
                errors.append(f"{cid}: test_manifest references missing {name}")
        runner_tmpl = " ".join(str(runner.get("test_command_template") or "").split())
        suite_tmpl = " ".join(str(tests_manifest.get("test_command_template") or "").split())
        if runner_tmpl and suite_tmpl and runner_tmpl != suite_tmpl:
            errors.append(
                f"{cid}: manifest and test_manifest disagree on test_command_template"
            )
        errors.extend(_check_undeclared_tests(cid, names, final_dir / "tests"))
        errors.extend(_check_substrates(cid, tests_manifest, final_dir / "tests"))
        errors.extend(_check_suite_wall_fields(cid, tests_manifest))
    return errors


def _declared_test_names(names: list) -> set[str]:
    declared: set[str] = set()
    for name in names:
        parts = Path(str(name)).parts
        if parts and parts[0] == "tests":
            parts = parts[1:]
        if parts:
            declared.add(parts[0])
    return declared


def _check_undeclared_tests(cid: str, names: list, tests_dir: Path) -> list[str]:
    if not tests_dir.is_dir():
        return []
    declared = _declared_test_names(names)
    errors: list[str] = []
    for child in sorted(tests_dir.iterdir()):
        if child.name == "__pycache__" or child.suffix == ".pyc":
            continue
        if child.name not in declared:
            errors.append(
                f"{cid}: tests/{child.name} is not declared in test_files or support_files"
            )
    return errors


def _privilege_hits(tests_dir: Path) -> list[str]:
    if not tests_dir.is_dir():
        return []
    pattern = re.compile(
        "|".join(
            rf"(?<![A-Za-z0-9_]){re.escape(item)}"
            for item in _PRIVILEGE_MARKERS
        )
    )
    hits: list[str] = []
    for path in sorted(tests_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pattern.search(text):
            hits.append(path.relative_to(tests_dir).as_posix())
    return hits


def _check_substrates(cid: str, tests_manifest: dict, tests_dir: Path) -> list[str]:
    raw = tests_manifest.get("judge_substrates")
    names: list[str] = []
    if raw is not None:
        if not isinstance(raw, list):
            return [f"{cid}: judge_substrates must be a list"]
        for item in raw:
            name = str(item or "").strip()
            if not name:
                continue
            if name not in KNOWN_PROVIDERS:
                return [f"{cid}: unknown judge_substrates provider {name!r}"]
            names.append(name)
    hits = _privilege_hits(tests_dir)
    if hits and not names:
        return [
            f"{cid}: hidden tests need a judge substrate "
            f"(declare judge_substrates); first hit {hits[0]}"
        ]
    return []


def _check_suite_wall_fields(cid: str, tests_manifest: dict) -> list[str]:
    errors: list[str] = []
    for key in ("suite_wall_seconds", "judge_timeout_sec"):
        if key not in tests_manifest:
            continue
        try:
            value = float(tests_manifest[key])
        except (TypeError, ValueError):
            errors.append(f"{cid}: {key} must be a non-negative number")
            continue
        if value < 0:
            errors.append(f"{cid}: {key} must be a non-negative number")
    measured = tests_manifest.get("suite_wall_measured_on")
    needs_measured = any(
        key in tests_manifest for key in ("suite_wall_seconds", "judge_timeout_sec")
    )
    if measured is None:
        if needs_measured:
            errors.append(
                f"{cid}: suite_wall_measured_on is required when "
                "suite_wall_seconds or judge_timeout_sec is set"
            )
        return errors
    if not isinstance(measured, dict):
        errors.append(f"{cid}: suite_wall_measured_on must be an object")
        return errors
    for field in ("arch", "os"):
        if not str(measured.get(field) or "").strip():
            errors.append(f"{cid}: suite_wall_measured_on.{field} is required")
    return errors


def check_case_warnings(case_dir: Path | str) -> list[str]:
    """Return non-fatal warnings. Privilege markers are errors (see substrates)."""
    case_dir = Path(case_dir)
    tests_dir = case_dir / "milestones" / "final" / "tests"
    if not tests_dir.is_dir():
        return []
    if any(path.name == "__pycache__" for path in tests_dir.rglob("__pycache__")):
        return [f"{case_dir.name}: tests/ contains __pycache__; delete it before sealing"]
    return []


def check_case_supply(case_dir: Path | str) -> list[str]:
    """Problems with *case_dir*'s supply manifest entry and lock (empty if clean).

    A full-suite run installs each case only from its lock, so a case without
    one, or with a lock recorded from a different install command, cannot run.
    """
    from .supply import SupplyError, case_files, case_inputs_digest, load_manifest, require_lock

    case_dir = Path(case_dir)
    try:
        case_files(load_manifest(), case_dir)
        require_lock("case", case_dir.name, case_inputs_digest(case_dir))
    except (SupplyError, OSError, ValueError) as exc:
        return [str(exc)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check case assets for runner defects.")
    parser.add_argument("--cases-root", type=Path, default=None)
    parser.add_argument("cases", nargs="*", help="Case ids; default is every case.")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    cases_root = args.cases_root or repo / "cases"
    if args.cases:
        dirs = [cases_root / name for name in args.cases]
    else:
        dirs = sorted(
            path
            for path in cases_root.iterdir()
            if path.is_dir() and (path / "source" / "manifest.json").is_file()
        )
    errors = 0
    for case_dir in dirs:
        if not case_dir.is_dir():
            print(f"error: case not found: {case_dir}", file=sys.stderr)
            errors += 1
            continue
        issues = check_case_assets(case_dir) + check_case_supply(case_dir)
        notes = check_case_warnings(case_dir)
        for item in issues:
            print(f"error: {item}")
        for item in notes:
            print(f"warning: {item}")
        if issues:
            errors += 1
        elif not notes:
            print(f"ok: {case_dir.name}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
