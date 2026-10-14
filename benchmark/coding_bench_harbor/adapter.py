"""Convert a zero2repo case into a Harbor (terminal-bench 2.0) task.

Asset mapping:

    cases/<case_id>/public/prd/                    -> <task>/environment/prd/
    cases/<case_id>/public/Interface_Contract.md  -> <task>/instruction.md
    cases/<case_id>/milestones/final/             -> <task>/tests/final/   (acceptance tests)

Hidden final tests live under Harbor ``tests/`` and are mounted at ``/tests``
only after the agent finishes.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from ._leakage import scan_leakage
from .brand import AUTHOR_NAME, TASK_NAMESPACE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from parse_prd import (  # noqa: E402
    PrdSource,
    read_prd_text_for_validation,
    resolve_prd_source,
    validate_prd_dir,
)
from artifact_contracts import (  # noqa: E402
    normalize_runner,
    render_test_command,
    resolve_final_acceptance_dir,
    resolve_gt_code_dir,
    validate_test_manifest,
)
from objective_gates import shutil_ignore_patterns  # noqa: E402

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "template"
CONTAINER_TESTS_FINAL = "/tests/final"


def default_cases_root() -> Path:
    """Directory that holds shipped case folders (``benchmark/cases``)."""
    return Path(__file__).resolve().parent.parent / "cases"


def iter_benchmark_case_dirs(cases_root: Path) -> list[Path]:
    """Return case directories that have ``source/manifest.json``.

    A directory whose name starts with ``_`` is treated as a draft and skipped.
    """
    root = Path(cases_root)
    if not root.is_dir():
        return []
    dirs: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if (path / "source" / "manifest.json").is_file():
            dirs.append(path)
    return dirs


def released_case_ids(cases_root: Path | None = None) -> frozenset[str]:
    """Case ids discovered under ``cases_root`` (default: ``benchmark/cases``)."""
    root = default_cases_root() if cases_root is None else Path(cases_root)
    return frozenset(path.name for path in iter_benchmark_case_dirs(root))


_COPY_IGNORE = shutil_ignore_patterns

_INSTRUCTION_PREAMBLE = """\
# Development Task

Build the project specified below, from scratch, in your current working
directory.

The hidden tests run against the workspace exactly as you leave it. See the
Build contract below for whether a build step is required and where outputs
must remain.

---

"""


_LEADING_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(\S+)\s*")


def _is_noop_build(cmd: str) -> bool:
    return str(cmd or "").strip() in {"", "true", ":"}


def _test_command_env(cmd: str) -> dict[str, str]:
    rest = str(cmd or "").lstrip()
    env: dict[str, str] = {}
    while True:
        match = _LEADING_ASSIGN.match(rest)
        if match is None:
            break
        env[match.group(1)] = match.group(2)
        rest = rest[match.end() :]
    return env


def _judge_test_command(case: "CaseAssets") -> str:
    """Prefer the sealed suite command over the published runner template."""
    manifest = case.acceptance.test_manifest or {}
    for key in ("test_command_template", "test_command"):
        text = str(manifest.get(key) or "").strip()
        if text:
            return text
    return str(case.runner.test_command or "").strip()


def _pythonpath_import_root(value: str) -> str:
    first = (value or "").split(":", 1)[0].strip() or "."
    if first in {".", ""}:
        return "/app"
    if first.startswith("/"):
        return first
    return f"/app/{first}"


def _launch_notes(test_env: dict[str, str] | None) -> str:
    env = dict(test_env or {})
    pythonpath = env.pop("PYTHONPATH", None)
    lines: list[str] = []
    if pythonpath is not None:
        root = _pythonpath_import_root(pythonpath)
        if pythonpath in {".", ""}:
            lines.append(
                "* The hidden tests run against `/app` as the working directory.\n"
            )
        else:
            lines.append(
                f"* The hidden tests are launched from `/app` with "
                f"`PYTHONPATH={pythonpath}`; your importable package(s) must "
                f"resolve from `{root}`.\n"
            )
    else:
        lines.append(
            "* The hidden tests run against `/app` as the working directory.\n"
        )
    for key, value in env.items():
        lines.append(
            f"* The hidden tests are launched with `{key}={value}`.\n"
        )
    return "".join(lines)


def build_contract_notes(
    build_command: str,
    workdir: str = ".",
    test_env: dict[str, str] | None = None,
) -> str:
    """Tell the agent how the judge locates build outputs. Judge never builds."""
    cmd = (build_command or "").strip()
    wd = (workdir or ".").strip() or "."
    header = (
        "## Build contract\n\n"
        "* The judge does **not** run any install or build step for you. "
        "The hidden acceptance tests run against your final `/app` exactly as "
        "you leave it.\n"
    )
    launch = _launch_notes(test_env)
    if _is_noop_build(cmd):
        return (
            header
            + "* There is no build step for this project.\n"
            + launch
        )
    workdir_line = ""
    if wd != ".":
        workdir_line = (
            f"* The hidden tests run with `/app/{wd}` as their working "
            "directory.\n"
        )
    return (
        header
        + "* They locate build outputs where this command would place them "
        "when run from the `/app` root:\n\n"
        f"  `{cmd}`\n\n"
        "  Leave those outputs in place before you submit. Do not clean the "
        "build tree.\n"
        + workdir_line
        + launch
    )


class AdapterError(RuntimeError):
    """Raised when a case cannot be converted into a valid Harbor task."""


@dataclass(frozen=True)
class GtMilestone:
    step: int
    step_dir: Path
    code_dir: Path


@dataclass(frozen=True)
class AcceptanceMilestone:
    """Full-picture acceptance tests under ``milestones/final/``."""
    acceptance_dir: Path
    tests_dir: Path
    test_files: list[Path]
    test_manifest_path: Path
    test_manifest: dict
    gt_step: int


@dataclass(frozen=True)
class RunnerMetadata:
    language: str
    install_command: str
    test_command: str
    workdir: str
    build_command: str = ""


@dataclass(frozen=True)
class CaseAssets:
    case_id: str
    language: str
    repository_url: str
    sensitive_terms: list[str]
    prd_source: PrdSource
    contract_path: Path
    runner: RunnerMetadata
    gt_milestone: GtMilestone
    acceptance: AcceptanceMilestone
    merged_prd_path: Path | None


def _load_step_test_files(step_dir: Path) -> tuple[list[Path], Path, dict]:
    """Load test file paths from test_manifest.json (required)."""
    tm_path = step_dir / "test_manifest.json"
    if not tm_path.exists():
        raise AdapterError(f"Missing test_manifest.json: {tm_path}")
    try:
        data = json.loads(tm_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdapterError(f"Invalid JSON in {tm_path}: {exc}") from exc

    manifest_errors = [
        i.message for i in validate_test_manifest(data, step_dir)
        if i.severity == "error"
    ]
    if manifest_errors:
        raise AdapterError(
            f"Invalid test_manifest.json for {step_dir.name}: " + "; ".join(manifest_errors)
        )

    files = [step_dir / rel for rel in data.get("test_files", [])]
    files = [f for f in files if f.is_file()]
    if not files:
        raise AdapterError(f"test_manifest.json lists no existing test files under {step_dir}")
    return files, tm_path, data


def _container_test_paths(
    manifest: dict, step_dir: Path, container_root: str
) -> list[str]:
    """Absolute in-container paths for each manifest test file."""
    paths: list[str] = []
    for rel in manifest.get("test_files", []):
        rel_path = Path(rel)
        src = step_dir / rel
        if not src.is_file():
            src = step_dir / "tests" / rel_path.name
        if not src.is_file():
            continue
        rel_under_final = src.relative_to(step_dir).as_posix()
        paths.append(f"{container_root}/{rel_under_final}")
    return paths


def _harbor_manifest(manifest: dict, step_dir: Path, container_root: str) -> dict:
    """Rewrite test_command so test file paths point at /tests/final/..."""
    out = dict(manifest)
    container_paths = _container_test_paths(manifest, step_dir, container_root)
    if not container_paths:
        out["test_command"] = manifest.get("test_command", "")
        return out

    cmd = manifest.get("test_command", "")
    if "{test_files}" in cmd or "{test_dir}" in cmd:
        out["test_command"] = render_test_command(
            cmd,
            test_files=container_paths,
            test_dir=f"{container_root}/tests",
        )
    elif container_paths:
        # Legacy manifests: replace case-relative paths; do not leave duplicates.
        for rel in manifest.get("test_files", []):
            rel_norm = Path(rel).as_posix()
            src = step_dir / rel_norm
            if not src.is_file():
                src = step_dir / "tests" / Path(rel).name
            if not src.is_file():
                continue
            rel_under_final = src.relative_to(step_dir).as_posix()
            container_path = f"{container_root}/{rel_under_final}"
            if rel_norm in cmd:
                cmd = cmd.replace(rel_norm, container_path)
            else:
                cmd = cmd.replace(Path(rel_norm).name, container_path)
        if not any(cp in cmd for cp in container_paths):
            cmd = f"{cmd} {' '.join(container_paths)}"
        out["test_command"] = " ".join(cmd.split())
    else:
        out["test_command"] = cmd
    return out


def discover_case(
    case_dir: Path,
    *,
    require_released: bool = True,
    require_gt: bool = True,
) -> CaseAssets:
    """Load and validate the assets of a zero2repo case directory."""
    case_dir = Path(case_dir).resolve()
    manifest_path = case_dir / "source" / "manifest.json"
    if not manifest_path.exists():
        raise AdapterError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    case_id = manifest.get("case_id") or case_dir.name
    if require_released:
        discovered = {path.resolve() for path in iter_benchmark_case_dirs(case_dir.parent)}
        if case_dir.resolve() not in discovered:
            raise AdapterError(
                f"Case '{case_id}' is not discoverable under {case_dir.parent} "
                "(need source/manifest.json; directory name must not start with '_')."
            )

    sensitive_terms = list(manifest.get("sensitive_terms", []))
    repository_url = manifest.get("repository_url", "")

    public_dir = case_dir / "public"
    prd_source = resolve_prd_source(public_dir)
    if prd_source is None:
        raise AdapterError(
            f"Missing PRD: expected {public_dir / 'prd/index.json'} "
            f"or {public_dir / 'Full_PRD.draft.md'}"
        )
    if prd_source.mode == "dir":
        errors = validate_prd_dir(prd_source.path)
        if errors:
            raise AdapterError(
                f"Invalid PRD directory {prd_source.path}: " + "; ".join(errors)
            )

    milestones_root = case_dir / "milestones"
    if not milestones_root.is_dir():
        raise AdapterError(f"Missing milestones directory: {milestones_root}")

    gt_info = resolve_gt_code_dir(milestones_root)
    if gt_info is None:
        if require_gt:
            raise AdapterError(
                f"Case '{case_id}' has no optional oracle GT under milestones/."
            )
        gt_step = 0
        gt_code_dir = milestones_root / "gt" / "code"
        gt_step_dir = milestones_root / "gt"
    else:
        gt_step, gt_code_dir = gt_info
        gt_step_dir = milestones_root / f"step_{gt_step}"
    gt_milestone = GtMilestone(
        step=gt_step,
        step_dir=gt_step_dir,
        code_dir=gt_code_dir,
    )

    acceptance_dir = resolve_final_acceptance_dir(milestones_root)
    if acceptance_dir is None:
        raise AdapterError(
            f"Case '{case_id}' has no final acceptance tests "
            f"(expected {milestones_root / 'final'}/test_manifest.json with tests/)."
        )
    test_files, tm_path, tm_data = _load_step_test_files(acceptance_dir)
    acceptance = AcceptanceMilestone(
        acceptance_dir=acceptance_dir,
        tests_dir=acceptance_dir / "tests",
        test_files=test_files,
        test_manifest_path=tm_path,
        test_manifest=tm_data,
        gt_step=gt_step,
    )

    runner_raw = normalize_runner(manifest.get("runner", {}))
    if not runner_raw or not runner_raw.get("test_command_template"):
        raise AdapterError(
            f"Case '{case_id}' manifest.runner is missing or invalid."
        )
    language = runner_raw.get("language_label") or runner_raw.get("language", "unknown")
    runner = RunnerMetadata(
        language=language,
        install_command=runner_raw.get("install_command", ""),
        test_command=runner_raw.get("test_command_template", ""),
        workdir=runner_raw.get("workdir", "."),
        build_command=runner_raw.get("build_command", ""),
    )

    contract_path = case_dir / "public" / "Interface_Contract.md"
    if not contract_path.exists():
        raise AdapterError(f"Missing Interface Contract: {contract_path}")

    merged_prd = case_dir / "public" / "Full_PRD.md"

    return CaseAssets(
        case_id=case_id,
        language=language,
        repository_url=repository_url,
        sensitive_terms=sensitive_terms,
        prd_source=prd_source,
        contract_path=contract_path,
        runner=runner,
        gt_milestone=gt_milestone,
        acceptance=acceptance,
        merged_prd_path=merged_prd if merged_prd.is_file() else None,
    )


def _full_prd_text(case: "CaseAssets") -> str:
    """Single-document PRD text for benchmark agent input.

    Prefers the merged holistic PRD (Stage B output at public/Full_PRD.md) which is the
    designated benchmark key input; falls back to concatenated per-step PRD sections.
    """
    merged = case.merged_prd_path
    if merged is not None and merged.is_file():
        text = merged.read_text(encoding="utf-8").strip()
        if text:
            return text
    return read_prd_text_for_validation(case.prd_source).strip()


def _build_instruction(case: CaseAssets, contract_text: str | None = None) -> str:
    parts = [_INSTRUCTION_PREAMBLE]
    parts.append(
        build_contract_notes(
            case.runner.build_command,
            case.runner.workdir,
            _test_command_env(_judge_test_command(case)),
        )
    )
    parts.append("\n")
    parts.append("# Product Requirements Document\n\n")
    parts.append(_full_prd_text(case))
    parts.append("\n\n")

    if contract_text:
        parts.append("---\n\n")
        parts.append("# Interface Contract\n\n")
        parts.append(contract_text.strip())
    parts.append("\n")
    return "".join(parts)


def _write_single_prd_file(task_dir: Path, prd_text: str) -> None:
    """Expose the same full PRD as one file under environment/prd/."""
    prd_env = task_dir / "environment" / "prd"
    prd_env.mkdir(parents=True, exist_ok=True)
    (prd_env / "Full_PRD.md").write_text(prd_text + "\n", encoding="utf-8")


def _build_task_toml(
    case: CaseAssets,
    *,
    difficulty: str,
    agent_timeout_sec: float,
    verifier_timeout_sec: float,
    build_timeout_sec: float,
    cpus: int,
    memory_mb: int,
    storage_mb: int,
) -> dict:
    acceptance = case.acceptance
    return {
        "schema_version": "1.1",
        "environment_mode": "separate",
        "artifacts": ["/app"],
        "task": {
            "name": f"{TASK_NAMESPACE}/{case.case_id}",
            "description": (
                f"Build a {case.language} project from scratch given a full "
                "development PRD. Scored by hidden final acceptance tests."
            ),
            "keywords": ["coding", "0-to-1", case.language],
            "authors": [{"name": AUTHOR_NAME}],
        },
        "metadata": {
            "case_id": case.case_id,
            "language": case.language,
            "difficulty": difficulty,
            "judge_mode": "final_tests",
            "final_step": acceptance.gt_step,
            "acceptance_stage": "final",
            "case_suite": "released-v1",
            "prd_delivery": "single_document",
            "benchmark_mode": "autonomous",
            "runner": {
                "install_command": case.runner.install_command,
                "build_command": case.runner.build_command,
                "test_command": case.runner.test_command,
                "workdir": case.runner.workdir,
            },
        },
        "verifier": {"timeout_sec": verifier_timeout_sec},
        "agent": {"timeout_sec": agent_timeout_sec},
        "environment": {
            "build_timeout_sec": build_timeout_sec,
            "cpus": cpus,
            "memory_mb": memory_mb,
            "storage_mb": storage_mb,
            "gpus": 0,
            "allow_internet": True,
            "mcp_servers": [],
        },
    }


def _copytree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=_COPY_IGNORE, dirs_exist_ok=True)


def _copy_final_tests(case: CaseAssets, task_tests_dir: Path) -> None:
    """Copy milestones/final acceptance tests into tests/final/."""
    acceptance = case.acceptance
    final_out = task_tests_dir / "final"
    if final_out.exists():
        shutil.rmtree(final_out)
    final_out.mkdir(parents=True)

    acceptance_src = acceptance.acceptance_dir
    for test_file in acceptance.test_files:
        rel = test_file.relative_to(acceptance_src)
        dest = final_out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_file, dest)

    for extra in ("run_acceptance.sh", "run_acceptance_meta.json"):
        src = acceptance_src / extra
        if src.is_file():
            shutil.copy2(src, final_out / extra)

    harbor_manifest = _harbor_manifest(
        acceptance.test_manifest, acceptance_src, CONTAINER_TESTS_FINAL
    )
    (final_out / "test_manifest.json").write_text(
        json.dumps(harbor_manifest, indent=2) + "\n", encoding="utf-8"
    )


def build_task(
    case_dir: Path | str,
    out_root: Path | str,
    *,
    allow_leakage: bool = False,
    force: bool = False,
    difficulty: str = "medium",
    agent_timeout_sec: float = 7200.0,
    verifier_timeout_sec: float = 600.0,
    build_timeout_sec: float = 600.0,
    cpus: int = 2,
    memory_mb: int = 16384,
    storage_mb: int = 10240,
    require_released: bool = True,
) -> Path:
    """Generate a Harbor task directory for *case_dir* under *out_root*."""
    case = discover_case(
        Path(case_dir),
        require_released=require_released,
        require_gt=False,
    )
    from cbrun.limits import case_test_timeout_sec

    per_case = case_test_timeout_sec(case.acceptance.test_manifest)
    if per_case:
        verifier_timeout_sec = max(float(verifier_timeout_sec), per_case)
    contract_text = case.contract_path.read_text(encoding="utf-8")

    prd_text = _full_prd_text(case)
    full_text = prd_text + ("\n" + contract_text if contract_text else "")
    if case.runner.build_command:
        full_text = f"{full_text}\n{case.runner.build_command}"
    hits = scan_leakage(full_text, case.sensitive_terms)
    if hits:
        summary = ", ".join(f"{h.term} (x{h.occurrences})" for h in hits)
        message = (
            f"Case '{case.case_id}' leaks source-identity terms: {summary}. "
            "Sanitize public/ documents or pass allow_leakage=True to override."
        )
        if not allow_leakage:
            raise AdapterError(message)
        print(f"WARNING: {message}")

    task_dir = Path(out_root).resolve() / case.case_id
    if task_dir.exists():
        if not force:
            raise AdapterError(
                f"Task directory already exists: {task_dir}. Use force=True to overwrite."
            )
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True)

    (task_dir / "instruction.md").write_text(
        _build_instruction(case, contract_text), encoding="utf-8"
    )

    _copytree(TEMPLATE_DIR / "environment", task_dir / "environment")
    _copytree(TEMPLATE_DIR / "tests", task_dir / "tests")
    _copytree(TEMPLATE_DIR / "solution", task_dir / "solution")

    _write_single_prd_file(task_dir, prd_text)

    harbor_dir = Path(__file__).resolve().parent
    for name in ("final_judge.py", "test_counts.py", "pytest_launcher.py"):
        shutil.copy2(harbor_dir / name, task_dir / "tests" / name)
    _copy_final_tests(case, task_dir / "tests")

    gt_dir = case.gt_milestone.code_dir
    if gt_dir.is_dir():
        _copytree(gt_dir, task_dir / "solution" / "gt")

    task_toml = _build_task_toml(
        case,
        difficulty=difficulty,
        agent_timeout_sec=agent_timeout_sec,
        verifier_timeout_sec=verifier_timeout_sec,
        build_timeout_sec=build_timeout_sec,
        cpus=cpus,
        memory_mb=memory_mb,
        storage_mb=storage_mb,
    )
    (task_dir / "task.toml").write_bytes(tomli_w.dumps(task_toml).encode("utf-8"))

    return task_dir
