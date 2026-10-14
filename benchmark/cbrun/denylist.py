"""Per-case upstream denylist: L3 install shims and L4 static scan."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .submit import CONTAINER_SUBMIT_PATH, SUBMIT_TOKEN

__all__ = [
    "DenylistSpec",
    "ImportHit",
    "InstalledHit",
    "ScanResult",
    "CONTAINER_DENYLIST_HASHES_PATH",
    "DEFAULT_FIX_RETRIES",
    "GITHUB_BLOCK_HOSTS",
    "OTHER_CODE_HOSTS",
    "GITHUB_MIRROR_HOSTS",
    "CODE_HOST_BLOCK_HOSTS",
    "build_fix_instruction",
    "build_access_fix_instruction",
    "CONTAINER_ACCESS_MONITOR_PATH",
    "render_access_monitor",
    "render_access_hook",
    "install_ban_hashes",
    "FORBIDDEN_IMPORT_BAN",
    "MissingDenylist",
    "load_denylist",
    "require_denylist",
    "normalize_pkg_name",
    "render_pip_shim",
    "render_conda_shim",
    "line_imports_token",
    "scan_workspace_imports",
    "validate_denylist_artifact",
    "validate_denylist_payload",
    "import_root_from_ban_token",
    "import_roots_from_ban_tokens",
    "is_command_like_token",
    "is_probeable_import_root",
    "denylist_hashes_from_payload",
    "render_strip_script",
    "render_npm_shim",
    "render_pip_module_hook",
    "probe_spec_from_payload",
    "probe_banned_imports",
    "probe_agent_runtime_leak",
    "log_probe_result",
    "ALLOWED_JUDGE_BANS",
]

ALLOWED_JUDGE_BANS = frozenset(
    {"socket", "subprocess", "network", "filesystem_outside_workspace"}
)

CONTAINER_DENYLIST_HASHES_PATH = "/opt/cbrun/denylist.hashes"
CONTAINER_STRIP_SCRIPT_PATH = "/opt/cbrun/strip_banned.py"
CONTAINER_PIP_HOOK_PATH = "/opt/cbrun/cbrun_denylist_hook.py"
CONTAINER_ACCESS_MONITOR_PATH = "/opt/cbrun/access_monitor.py"
CONTAINER_ACCESS_HOOK_PATH = "/opt/cbrun/cbrun_access_hook.py"
SHIM_BIN_DIR = "/opt/cbrun/bin"
PIP_BLOCK_CMDS = frozenset({"install", "i", "add", "download", "wheel"})
_PROBEABLE_ROOT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_VERSION_ROOT = re.compile(r"^v\d+$")
_COMMAND_LIKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEADER_SUFFIXES = (".h", ".hh", ".hpp", ".hxx", ".cpp", ".cc", ".cxx")
DEFAULT_FIX_RETRIES = 1

# Hostnames pointed at 0.0.0.0 in the solve container's /etc/hosts, so a clone
# or download of the upstream repository fails at run time. Only code hosts and
# their mirrors are listed: package registries (PyPI, npm, Go proxy, crates.io,
# ...) stay reachable because ordinary dependency installs need them; the
# post-trial transcript scan (``transcript_scan``) reports source archives
# fetched from them.
GITHUB_BLOCK_HOSTS = (
    "github.com",
    "www.github.com",
    "api.github.com",
    "codeload.github.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "gist.githubusercontent.com",
    "media.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "objects-origin.githubusercontent.com",
    "uploads.github.com",
)

# Other public code hosts.
OTHER_CODE_HOSTS = (
    "gitlab.com",
    "www.gitlab.com",
    "gitee.com",
    "www.gitee.com",
    "bitbucket.org",
    "www.bitbucket.org",
    "api.bitbucket.org",
    "sourcegraph.com",
    "www.sourcegraph.com",
    "codeberg.org",
    "git.sr.ht",
)

# Well-known GitHub mirrors and download proxies.
GITHUB_MIRROR_HOSTS = (
    "ghproxy.com",
    "mirror.ghproxy.com",
    "ghproxy.net",
    "gh-proxy.com",
    "ghfast.top",
    "hub.fastgit.org",
    "hub.fastgit.xyz",
    "download.fastgit.org",
    "raw.fastgit.org",
    "kkgithub.com",
    "raw.kkgithub.com",
    "bgithub.xyz",
    "gitclone.com",
    "githubfast.com",
)

# Everything ``--block-github`` (alias ``--block-code-hosts``) blocks.
CODE_HOST_BLOCK_HOSTS = GITHUB_BLOCK_HOSTS + OTHER_CODE_HOSTS + GITHUB_MIRROR_HOSTS

# Scan only source-like files under /app.
_SOURCE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".cu",
    ".cuh",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hh",
    ".rs",
    ".go",
    ".java",
    ".cs",
    ".rb",
    ".php",
    ".dart",
    ".swift",
    ".kt",
    ".scala",
    ".zig",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".tox",
}

# import_ban must target the upstream *product* under test, not general toolchain/stdlib
# layers that the Interface Contract may explicitly allow (e.g. libcu++ ``cuda::`` on CUDA cases).
FORBIDDEN_IMPORT_BAN = frozenset(
    {
        "cuda::",
        "cuda/",
        "std::",
        "numpy",
        "numpy/",
        "torch",
        "torch::",
    }
)


def validate_denylist_payload(payload: dict) -> list[str]:
    """Return policy violations for a denylist.json object (empty if OK)."""
    errors: list[str] = []
    case_id = str(payload.get("case_id") or "?")
    for token in payload.get("import_ban") or []:
        text = str(token).strip()
        if not text:
            errors.append(f"{case_id}: import_ban contains empty token")
            continue
        if text in FORBIDDEN_IMPORT_BAN:
            errors.append(
                f"{case_id}: import_ban must not include general infrastructure token {text!r}"
            )
    return errors


def _normalize_identity_fragment(text: str) -> str:
    """Loose normalization for overlap checks between ban tokens and case identity."""
    t = str(text).strip().lower().rstrip(":").rstrip("/")
    t = t.replace("_", "-").replace(".", "-")
    t = re.sub(r"[^a-z0-9-]+", "-", t)
    while "--" in t:
        t = t.replace("--", "-")
    return t.strip("-")


def _ban_token_matches_identity(token: str, manifest: dict) -> bool:
    """True when a ban token plausibly targets this case's upstream product identity."""
    norm = _normalize_identity_fragment(token)
    if len(norm) < 3:
        return False

    hay: set[str] = set()
    for term in manifest.get("sensitive_terms") or []:
        hay.add(_normalize_identity_fragment(term))
    for key in ("repo_slug", "repository_url", "case_id"):
        value = manifest.get(key)
        if value:
            hay.add(_normalize_identity_fragment(str(value)))
    init = manifest.get("init_metadata") or {}
    for key in ("suggested_neutral_name", "tech_stack"):
        value = init.get(key)
        if value:
            hay.add(_normalize_identity_fragment(str(value)))

    for h in hay:
        if len(h) < 3:
            continue
        if norm in h or h in norm:
            return True

    for part in re.split(r"[/\\:]+", str(token).lower()):
        part_norm = _normalize_identity_fragment(part)
        if len(part_norm) < 3:
            continue
        for h in hay:
            if len(h) < 3:
                continue
            if part_norm in h or h in part_norm:
                return True
    return False


def validate_denylist_artifact(
    payload: dict,
    manifest: dict,
    *,
    case_id: str | None = None,
) -> list[str]:
    """Shape + policy + identity overlap checks for a Stage G denylist.json artifact."""
    errors = list(validate_denylist_payload(payload))
    cid = str(payload.get("case_id") or case_id or "?")
    expected_case = case_id or str(manifest.get("case_id") or "")

    if int(payload.get("schema_version") or 0) != 1:
        errors.append(f"{cid}: schema_version must be 1")
    if expected_case and payload.get("case_id") != expected_case:
        errors.append(f"{cid}: case_id must be {expected_case!r}")
    if not str(payload.get("ecosystem") or "").strip():
        errors.append(f"{cid}: ecosystem is required")

    install = [str(x).strip() for x in (payload.get("install_ban") or []) if str(x).strip()]
    imports = [str(x).strip() for x in (payload.get("import_ban") or []) if str(x).strip()]
    if not install and not imports:
        errors.append(f"{cid}: at least one install_ban or import_ban token required")

    bans = install + imports
    if bans and not any(_ban_token_matches_identity(token, manifest) for token in bans):
        errors.append(
            f"{cid}: no denylist token overlaps case identity metadata "
            "(sensitive_terms / repo identity)"
        )
    errors.extend(_validate_runtime_equivalents(payload, imports, cid))
    return errors


_RUNTIME_FAMILIES = frozenset({"python3", "node", "system"})


def _validate_runtime_equivalents(
    payload: dict, import_ban: list[str], case_id: str
) -> list[str]:
    raw = payload.get("runtime_equivalents")
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        return [f"{case_id}: runtime_equivalents must be a list"]
    ban_roots = {
        (import_root_from_ban_token(tok) or "").strip()
        for tok in import_ban
        if str(tok).strip()
    }
    ban_roots.discard("")
    errors: list[str] = []
    for index, row in enumerate(raw):
        prefix = f"{case_id}: runtime_equivalents[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        root = str(row.get("import_root") or "").strip()
        runtime = str(row.get("runtime") or "").strip()
        evidence = str(row.get("evidence") or "").strip()
        if not root:
            errors.append(f"{prefix}.import_root is required")
        if runtime not in _RUNTIME_FAMILIES:
            errors.append(
                f"{prefix}.runtime must be one of {sorted(_RUNTIME_FAMILIES)}"
            )
        if not evidence:
            errors.append(f"{prefix}.evidence is required")
        if root and root not in ban_roots and root not in import_ban:
            errors.append(
                f"{prefix}.import_root {root!r} must also appear in import_ban"
            )
    return errors


_PY_SUFFIXES = {".py", ".pyi"}
_JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_C_SUFFIXES = {".c", ".h", ".hpp", ".hh", ".cc", ".cxx", ".cpp", ".cu", ".cuh"}
_HASH_COMMENT_SUFFIXES = _PY_SUFFIXES | {".rb", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".toml"}
_SLASH_COMMENT_SUFFIXES = (
    _JS_SUFFIXES | _C_SUFFIXES | {".java", ".kt", ".scala", ".cs", ".go", ".rs", ".swift", ".dart", ".zig"}
)


def _strip_hash_or_slash_comment(line: str, *, slash: bool, hash_comment: bool) -> str:
    """Drop trailing comments; keep string literals so import specifiers stay visible."""
    stripped = line.strip()
    if not stripped:
        return ""
    if hash_comment and stripped.startswith("#"):
        return ""
    if slash and stripped.startswith("//"):
        return ""
    out: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    idx = 0
    while idx < len(line):
        ch = line[idx]
        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
        elif not in_single and not in_double and not in_backtick:
            if hash_comment and ch == "#":
                break
            if slash and line.startswith("//", idx):
                break
        out.append(ch)
        idx += 1
    return "".join(out)


def _strip_quoted_spans(text: str) -> str:
    """Replace quoted spans with spaces so leftover tokens are real code."""
    out: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    for ch in text:
        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
            out.append(" ")
            continue
        if ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
            out.append(" ")
            continue
        if ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            out.append(" ")
            continue
        out.append(" " if (in_single or in_double or in_backtick) else ch)
    return "".join(out)


def _comment_mode(suffix: str) -> tuple[bool, bool]:
    hash_comment = suffix in _HASH_COMMENT_SUFFIXES
    slash = suffix in _SLASH_COMMENT_SUFFIXES
    if suffix in {".php"}:
        hash_comment = True
        slash = True
    return hash_comment, slash


def _code_minus_comments(line: str, suffix: str) -> str:
    hash_comment, slash = _comment_mode(suffix)
    return _strip_hash_or_slash_comment(line, slash=slash, hash_comment=hash_comment)


def _python_imports_token(code: str, token: str) -> bool:
    pattern = rf"(?:^|;)\s*(?:import|from)\s+(?:[A-Za-z_][\w]*\.)*{re.escape(token)}\b"
    return re.search(pattern, code) is not None


def _js_imports_token(code: str, token: str) -> bool:
    base = token.rstrip("/")
    quoted = rf"""['"](?:{re.escape(base)})(?:['"/]|$)"""
    patterns = (
        rf"(?:^|;)\s*import\s+(?:[^'\"\n]+?\s+from\s+)?{quoted}",
        rf"(?:^|;)\s*export\s+(?:[^'\"\n]+?\s+from\s+){quoted}",
        rf"\brequire\s*\(\s*{quoted}",
        rf"\bimport\s*\(\s*{quoted}",
    )
    return any(re.search(p, code) for p in patterns)


def _go_imports_token(code: str, token: str) -> bool:
    base = token.rstrip("/")
    return re.search(rf"""(?:^|;)\s*import\s+(?:\w+\s+)?["`](?:{re.escape(base)})""", code) is not None


def _rust_imports_token(code: str, token: str) -> bool:
    return (
        re.search(rf"(?:^|;)\s*(?:use|extern\s+crate)\s+{re.escape(token)}\b", code) is not None
    )


def _jvm_imports_token(code: str, token: str) -> bool:
    return re.search(rf"(?:^|;)\s*import\s+(?:static\s+)?{re.escape(token)}[.;]", code) is not None


def _c_includes_token(code: str, token: str) -> bool:
    base = token.rstrip("/")
    return re.search(rf"""#\s*include\s*[<"]{re.escape(base)}""", code) is not None


def _ruby_imports_token(code: str, token: str) -> bool:
    base = token.rstrip("/")
    quoted = rf"""['"](?:{re.escape(base)})(?:['"/]|$)"""
    return re.search(rf"\b(?:require|require_relative)\s*\(?\s*{quoted}", code) is not None


def _php_imports_token(code: str, token: str) -> bool:
    if re.search(rf"(?:^|;)\s*use\s+{re.escape(token)}\b", code):
        return True
    return _ruby_imports_token(code, token)


def _csharp_imports_token(code: str, token: str) -> bool:
    return re.search(rf"(?:^|;)\s*using\s+{re.escape(token)}\b", code) is not None


def _path_import_hit(code: str, token: str) -> bool:
    if token not in code:
        return False
    return bool(
        re.search(
            rf"""(?:import|from|require|require_relative|include|use)\b.*{re.escape(token)}""",
            code,
        )
    )


def line_imports_token(line: str, token: str, suffix: str = ".py") -> bool:
    """True when *line* is a real import/require/use of *token*, not prose."""
    code = _code_minus_comments(line, suffix)
    if not code.strip():
        return False
    if token.endswith("::"):
        return token in _strip_quoted_spans(code)
    if token.endswith("/") or "\\" in token:
        return _path_import_hit(code, token)
    ext = suffix.lower()
    if ext in _PY_SUFFIXES:
        return _python_imports_token(code, token)
    if ext in _JS_SUFFIXES:
        return _js_imports_token(code, token)
    if ext == ".go":
        return _go_imports_token(code, token)
    if ext == ".rs":
        return _rust_imports_token(code, token)
    if ext in {".java", ".kt", ".scala"}:
        return _jvm_imports_token(code, token)
    if ext in _C_SUFFIXES:
        return _c_includes_token(code, token)
    if ext == ".zig":
        return _js_imports_token(code, token)
    if ext == ".rb":
        return _ruby_imports_token(code, token)
    if ext == ".php":
        return _php_imports_token(code, token)
    if ext == ".cs":
        return _csharp_imports_token(code, token)
    if ext in {".dart", ".swift"}:
        return _jvm_imports_token(code, token) or _js_imports_token(code, token)
    # Unknown / data files: only structured import forms, never a bare word.
    return (
        _python_imports_token(code, token)
        or _js_imports_token(code, token)
        or _path_import_hit(code, token)
    )


@dataclass(frozen=True)
class DenylistSpec:
    case_id: str
    ecosystem: str
    install_ban: tuple[str, ...]
    import_ban: tuple[str, ...]
    notes: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.install_ban or self.import_ban)


@dataclass(frozen=True)
class ImportHit:
    token: str
    path: str
    line: int
    line_text: str


@dataclass(frozen=True)
class InstalledHit:
    package: str


@dataclass
class ScanResult:
    import_hits: list[ImportHit] = field(default_factory=list)
    installed_warnings: list[InstalledHit] = field(default_factory=list)

    @property
    def has_hard_violation(self) -> bool:
        return bool(self.import_hits)


def install_ban_hashes(install_ban: tuple[str, ...] | list[str]) -> list[str]:
    """SHA-256 hex digests of normalized install-ban package names (for image baking)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in install_ban:
        norm = normalize_pkg_name(str(raw))
        if not norm:
            continue
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            out.append(digest)
    return out


def install_ban_hashes_from_file(denylist_path: Path) -> list[str]:
    if not denylist_path.is_file():
        return []
    data = json.loads(denylist_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return denylist_hashes_from_payload(data)


def is_probeable_import_root(root: str) -> bool:
    """True when *root* is safe to pass to find_spec / require.resolve / rmdir."""
    text = str(root or "").strip()
    if text.startswith("@") and "/" in text:
        parts = [p for p in text.split("/") if p]
        if len(parts) != 2:
            return False
        scoped = parts[0][1:] if parts[0].startswith("@") else parts[0]
        return is_probeable_import_root(scoped) and is_probeable_import_root(parts[1])
    if len(text) < 3:
        return False
    if not _PROBEABLE_ROOT.fullmatch(text):
        return False
    if _VERSION_ROOT.fullmatch(text):
        return False
    return True


def is_command_like_token(token: str) -> bool:
    """True when *token* may be a PATH binary (not a header or C++ qualifier)."""
    text = str(token or "").strip().rstrip("/")
    if not text or "/" in text or "::" in text:
        return False
    if any(text.endswith(suf) for suf in _HEADER_SUFFIXES):
        return False
    return bool(_COMMAND_LIKE.fullmatch(text))


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def denylist_hashes_from_payload(payload: dict) -> list[str]:
    """Hashes for install_ban names plus probeable import roots / raw filenames."""
    seen: set[str] = set()
    out: list[str] = []

    def add(text: str) -> None:
        value = str(text or "").strip()
        if not value:
            return
        digest = _hash_text(value)
        if digest not in seen:
            seen.add(digest)
            out.append(digest)

    for raw in payload.get("install_ban") or []:
        norm = normalize_pkg_name(str(raw))
        if norm:
            add(norm)
    for raw in payload.get("import_ban") or []:
        token = str(raw).strip()
        if not token:
            continue
        add(token.lower().rstrip("/"))
        base = Path(token).name.lower()
        if base:
            add(base)
        root = import_root_from_ban_token(token)
        if root and is_probeable_import_root(root):
            add(root.lower())
            add(normalize_pkg_name(root))
    return out


def normalize_pkg_name(name: str) -> str:
    """PEP 503-ish normalization for pip/conda package names."""
    text = name.strip().lower()
    text = text.split("[", 1)[0]  # extras
    text = text.split("@", 1)[0]  # direct URL
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.replace("_", "-").replace(".", "-")


def load_denylist(case_dir: Path | str) -> DenylistSpec | None:
    path = Path(case_dir) / "source" / "denylist.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    install = tuple(str(x) for x in (data.get("install_ban") or []) if str(x).strip())
    imports = tuple(str(x) for x in (data.get("import_ban") or []) if str(x).strip())
    if not install and not imports:
        return None
    return DenylistSpec(
        case_id=str(data.get("case_id") or Path(case_dir).name),
        ecosystem=str(data.get("ecosystem") or ""),
        install_ban=install,
        import_ban=imports,
        notes=str(data.get("notes") or ""),
    )


class MissingDenylist(RuntimeError):
    """source/denylist.json is absent or has no ban entries."""


def require_denylist(case_dir: Path | str) -> DenylistSpec:
    """Load the denylist or raise. Missing / empty is not a clean scan."""
    path = Path(case_dir) / "source" / "denylist.json"
    spec = load_denylist(case_dir)
    if spec is not None:
        return spec
    if not path.is_file():
        raise MissingDenylist(
            f"source/denylist.json is missing at {path}. "
            "Every released case tracks this file; restore it from git, "
            "or pass --no-enforce-denylist to skip the scan."
        )
    raise MissingDenylist(
        f"source/denylist.json at {path} has no install_ban or import_ban. "
        "An empty denylist is not a pass. Fix the file or pass "
        "--no-enforce-denylist."
    )


def _normalized_ban_set(spec: DenylistSpec) -> set[str]:
    return {normalize_pkg_name(x) for x in spec.install_ban}


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        files.append(path)
    return files


def scan_workspace_imports(workspace: Path, spec: DenylistSpec) -> list[ImportHit]:
    hits: list[ImportHit] = []
    if not spec.import_ban:
        return hits
    for file_path in _iter_source_files(workspace):
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        suffix = file_path.suffix.lower()
        for line_no, line in enumerate(lines, start=1):
            for token in spec.import_ban:
                if line_imports_token(line, token, suffix):
                    hits.append(
                        ImportHit(
                            token=token,
                            path=str(file_path),
                            line=line_no,
                            line_text=line.strip()[:200],
                        )
                    )
                    break
    return hits


def scan_installed_warnings(packages: list[str], spec: DenylistSpec) -> list[InstalledHit]:
    if not spec.install_ban:
        return []
    banned = _normalized_ban_set(spec)
    warnings: list[InstalledHit] = []
    seen: set[str] = set()
    for pkg in packages:
        norm = normalize_pkg_name(pkg)
        if norm in banned and norm not in seen:
            seen.add(norm)
            warnings.append(InstalledHit(package=pkg))
    return warnings


def build_fix_instruction(base_instruction: str, hits: list[ImportHit]) -> str:
    lines = [
        base_instruction.rstrip(),
        "",
        "---",
        "",
        "## Denylist violation — fix required before submission",
        "",
        "Your current workspace uses upstream implementations that must be removed.",
        "Implement the required behavior yourself from the PRD and Interface Contract.",
        "Do not install, import, or wrap the upstream product listed below.",
        "",
        "Violations detected:",
        "",
    ]
    for hit in hits:
        lines.append(f"- `{hit.token}` at `{hit.path}` line {hit.line}: `{hit.line_text}`")
    lines.extend(
        [
            "",
            "Remove these upstream dependencies and re-implement the functionality.",
            f"When the fix is complete, write the submit file again at `{CONTAINER_SUBMIT_PATH}` "
            f"with exactly the one-line contents `{SUBMIT_TOKEN}`. Ending the session is not a "
            "submission.",
            "",
        ]
    )
    return "\n".join(lines)


def build_access_fix_instruction(base_instruction: str, events: list[dict]) -> str:
    """Instruction for the round after a monitored access stopped the agent."""
    lines = [
        base_instruction.rstrip(),
        "",
        "---",
        "",
        "## Stopped: access to a banned implementation",
        "",
        "Your previous session was stopped because the access monitor observed",
        "the following. This is your first and only warning.",
        "",
    ]
    for event in events[:10]:
        lines.append(f"- {event.get('message') or event.get('kind')}")
    if len(events) > 10:
        lines.append(f"- ... and {len(events) - 10} more")
    lines.extend(
        [
            "",
            "Why this is forbidden: the files above belong to an existing implementation",
            "of the product you must build. Reading, copying, disassembling, decompiling,",
            "or using such an implementation as a dependency or an oracle (for example",
            "running it to compare outputs) is not allowed, whatever tool or language does",
            "it. Stopping, altering, or evading the access monitor is also forbidden.",
            "",
            "Continue from the current state of the workspace. Build the behavior yourself",
            "from the PRD and the Interface Contract. Another violation fails this attempt.",
            f"When you are done, write the submit file again at `{CONTAINER_SUBMIT_PATH}` "
            f"with exactly the one-line contents `{SUBMIT_TOKEN}`. Ending the session is not a "
            "submission.",
            "",
        ]
    )
    return "\n".join(lines)


_PIP_SHIM = r"""#!/bin/bash
set -eu
HASHES="/opt/cbrun/denylist.hashes"
SHIM_DIR="/opt/cbrun/bin"
if [[ ! -f "$HASHES" ]]; then
  REAL="$(type -ap pip 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
  exec "${REAL:-/usr/bin/pip}" "$@"
fi
python3 - "$@" <<'PY'
import hashlib, re, sys
from pathlib import Path

ban = {ln.strip() for ln in Path("/opt/cbrun/denylist.hashes").read_text().splitlines() if ln.strip()}

def norm(name: str) -> str:
    name = name.strip().lower().split("[", 1)[0].split("@", 1)[0]
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    return name.replace("_", "-").replace(".", "-")

def check(name: str) -> None:
    digest = hashlib.sha256(norm(name).encode()).hexdigest()
    if digest in ban:
        print(f"[cbrun denylist] blocked install of upstream package: {name}", file=sys.stderr)
        print("[cbrun denylist] implement this functionality yourself; do not reuse the upstream product.", file=sys.stderr)
        sys.exit(1)

argv = sys.argv[1:]
i = 0
install_cmds = {"install", "i", "add", "download", "wheel"}
while i < len(argv):
    tok = argv[i]
    if tok in install_cmds:
        i += 1
        while i < len(argv):
            arg = argv[i]
            if arg.startswith("-"):
                if arg in ("-r", "--requirement") and i + 1 < len(argv):
                    req = Path(argv[i + 1])
                    if req.is_file():
                        for line in req.read_text().splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                check(line.split(";", 1)[0].strip())
                    i += 2
                    continue
                i += 1
                continue
            check(arg)
            i += 1
        break
    i += 1
PY
REAL="$(type -ap pip 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
exec "${REAL:-/usr/bin/pip}" "$@"
"""

_CONDA_SHIM = r"""#!/bin/bash
set -eu
HASHES="/opt/cbrun/denylist.hashes"
SHIM_DIR="/opt/cbrun/bin"
if [[ ! -f "$HASHES" ]]; then
  REAL="$(type -ap conda 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
  exec "${REAL:-conda}" "$@"
fi
python3 - "$@" <<'PY'
import hashlib, re, sys
from pathlib import Path

ban = {ln.strip() for ln in Path("/opt/cbrun/denylist.hashes").read_text().splitlines() if ln.strip()}

def norm(name: str) -> str:
    name = name.strip().lower().split("[", 1)[0].split("@", 1)[0]
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    return name.replace("_", "-").replace(".", "-")

def check(name: str) -> None:
    digest = hashlib.sha256(norm(name).encode()).hexdigest()
    if digest in ban:
        print(f"[cbrun denylist] blocked install of upstream package: {name}", file=sys.stderr)
        print("[cbrun denylist] implement this functionality yourself; do not reuse the upstream product.", file=sys.stderr)
        sys.exit(1)

argv = sys.argv[1:]
if argv and argv[0] in ("install", "create"):
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        check(arg)
PY
REAL="$(type -ap conda 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
exec "${REAL:-conda}" "$@"
"""

_NPM_SHIM = r"""#!/bin/bash
set -eu
HASHES="/opt/cbrun/denylist.hashes"
SHIM_DIR="/opt/cbrun/bin"
SELF="$(basename "$0")"
if [[ ! -f "$HASHES" ]]; then
  REAL="$(type -ap "$SELF" 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
  exec "${REAL:-$SELF}" "$@"
fi
python3 - "$@" <<'PY'
import hashlib, re, sys
from pathlib import Path

ban = {ln.strip() for ln in Path("/opt/cbrun/denylist.hashes").read_text().splitlines() if ln.strip()}

def norm(name: str) -> str:
    name = name.strip().lower().split("[", 1)[0]
    if name.startswith("@"):
        return name.split("?", 1)[0]
    name = name.split("@", 1)[0]
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    return name.replace("_", "-").replace(".", "-")

def check(name: str) -> None:
    digest = hashlib.sha256(norm(name).encode()).hexdigest()
    raw = hashlib.sha256(name.strip().lower().encode()).hexdigest()
    if digest in ban or raw in ban:
        print(f"[cbrun denylist] blocked install of upstream package: {name}", file=sys.stderr)
        print("[cbrun denylist] implement this functionality yourself; do not reuse the upstream product.", file=sys.stderr)
        sys.exit(1)

argv = sys.argv[1:]
i = 0
install_cmds = {"install", "i", "add"}
while i < len(argv):
    tok = argv[i]
    if tok in install_cmds:
        i += 1
        while i < len(argv):
            arg = argv[i]
            if arg.startswith("-"):
                i += 1
                continue
            check(arg)
            i += 1
        break
    i += 1
PY
REAL="$(type -ap "$SELF" 2>/dev/null | grep -v "$SHIM_DIR" | head -1 || true)"
exec "${REAL:-$SELF}" "$@"
"""

# Shared by the strip script and the access monitor: find image artefacts whose
# names hash to the denylist set. Never contains plaintext product names.
_DISCOVERY_LIB = r'''
HASHES = Path(os.environ.get("CBRUN_DENYLIST_HASHES", "/opt/cbrun/denylist.hashes"))
# Directories where packages ship private copies of their dependencies.
VENDOR_DIRS = {"_vendor", "vendor", "_vendored", "_vendored_packages", "extern"}
# Interpreters whose packages cannot be uninstalled (agent CLIs, extra envs).
EXTRA_PYTHON_GLOBS = (
    "/opt/conda/envs/*/bin/python3",
    "/root/.local/share/uv/python/*/bin/python3",
    "/root/.local/share/uv/tools/*/bin/python3",
)
# Global Node trees; nested node_modules below them are searched too.
NODE_ROOTS = (
    "/usr/local/lib/node_modules",
    "/usr/lib/node_modules",
    "/opt/nodejs/lib/node_modules",
    "/opt/cbrun/runtime/node/lib/node_modules",
)
WORKSPACE = "/app"


def _norm(name: str) -> str:
    text = name.strip().lower().split("[", 1)[0].split("@", 1)[0]
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.replace("_", "-").replace(".", "-")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_ban() -> set[str]:
    if not HASHES.is_file():
        return set()
    return {ln.strip() for ln in HASHES.read_text(encoding="utf-8").splitlines() if ln.strip()}


BAN = _load_ban()


def _banned(name: str) -> bool:
    raw = str(name or "").strip().lower()
    if not raw:
        return False
    return _digest(raw) in BAN or _digest(_norm(raw)) in BAN


def _pythons() -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for cand in ("/opt/conda/bin/python3", "/usr/bin/python3", shutil.which("python3") or ""):
        if cand and os.path.isfile(cand) and cand not in seen:
            seen.add(cand)
            found.append(cand)
    return found


def _run_json(argv: list[str]) -> object | None:
    try:
        out = subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def _all_pythons() -> list[str]:
    found = _pythons()
    seen = {os.path.realpath(os.path.dirname(p)) for p in found}
    for pattern in EXTRA_PYTHON_GLOBS:
        for cand in sorted(glob.glob(pattern)):
            # uv tool venvs symlink python3 to a shared base; keep both, they
            # report different site-packages.
            key = os.path.realpath(os.path.dirname(cand))
            if os.path.isfile(cand) and key not in seen:
                seen.add(key)
                found.append(cand)
    return found


def _python_layout(py: str) -> dict | None:
    info = _run_json(
        [
            py,
            "-c",
            "import json, site, sysconfig; "
            "print(json.dumps({'stdlib': sysconfig.get_path('stdlib'), "
            "'sites': list(site.getsitepackages())}))",
        ]
    )
    return info if isinstance(info, dict) else None


def _module_name(path: Path) -> str | None:
    if path.is_symlink():
        return None
    if path.is_dir():
        return path.name
    if path.suffix == ".py":
        return path.stem
    return None


def _banned_children(parent: Path, name_of):
    if not parent.is_dir():
        return
    try:
        children = sorted(parent.iterdir())
    except OSError:
        return
    for child in children:
        name = name_of(child)
        if name and _banned(name):
            yield child


def banned_python_artefacts(name_of=_module_name):
    """Yield ``(python, path)`` for banned modules in every interpreter's
    stdlib, site-packages, and vendor directories below site-packages."""
    for py in _all_pythons():
        info = _python_layout(py)
        if info is None:
            continue
        if info.get("stdlib"):
            for child in _banned_children(Path(str(info["stdlib"])), name_of):
                yield py, child
        for site_dir in info.get("sites") or []:
            root = Path(str(site_dir))
            # Anything still here after uninstall is needed by an agent CLI.
            for child in _banned_children(root, name_of):
                yield py, child
            for dirpath, dirnames, _files in os.walk(root):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                if os.path.basename(dirpath) in VENDOR_DIRS:
                    for child in _banned_children(Path(dirpath), name_of):
                        yield py, child


def banned_node_artefacts():
    """Yield banned package directories in global and nested node_modules."""
    for base in NODE_ROOTS:
        for dirpath, dirnames, _files in os.walk(base):
            if os.path.basename(dirpath) != "node_modules":
                continue
            keep: list[str] = []
            for name in sorted(dirnames):
                path = Path(dirpath) / name
                if path.is_symlink():
                    continue
                if name.startswith("@"):
                    try:
                        scoped = sorted(p.name for p in path.iterdir() if p.is_dir())
                    except OSError:
                        scoped = []
                    for sub in scoped:
                        if _banned(f"{name}/{sub}") or _banned(sub):
                            yield path / sub
                    keep.append(name)
                elif _banned(name):
                    yield path
                else:
                    keep.append(name)
            dirnames[:] = keep
'''

_STRIP_MAIN = r'''

def _uninstall(py: str, dists: list[str]) -> None:
    if not dists:
        return
    subprocess.run(
        [py, "-m", "pip", "uninstall", "-y", "--break-system-packages", *dists],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _maybe_rm(path: Path) -> None:
    name = path.name
    stem = name
    for suf in (".dist-info", ".egg-info", ".json", ".so"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    candidates = {name.lower(), stem.lower()}
    head = re.match(r"^([A-Za-z0-9_.]+)", stem)
    if head:
        candidates.add(head.group(1).lower())
    named = re.match(r"^([A-Za-z0-9_.]+(?:-[A-Za-z][A-Za-z0-9_.]+)*)-\d", stem)
    if named:
        candidates.add(named.group(1).lower())
    if name.startswith("lib") and ".so" in name:
        core = name[3:].split(".so", 1)[0]
        candidates.add(core.lower())
        candidates.add(("lib" + core).lower())
    if not any(_banned(item) for item in candidates):
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        print(f"[cbrun] removed leftover {_digest(name)[:8]}", flush=True)
    except OSError:
        pass


def _scan_dir(path: Path) -> None:
    if not path.is_dir():
        return
    try:
        children = list(path.iterdir())
    except OSError:
        return
    for child in children:
        _maybe_rm(child)


_SOURCELESS_DONE: set[str] = set()


def _sourceless(py: str, path: Path) -> None:
    """Keep *path* importable by *py* but drop its readable source.

    Stdlib modules, vendored copies and agent-runtime dependencies are still
    imported by the toolchain, so they are compiled to legacy ``.pyc`` files
    next to the source and the ``.py`` files are removed.
    """
    key = os.path.realpath(path)
    if key in _SOURCELESS_DONE:
        return
    _SOURCELESS_DONE.add(key)
    sources = [path] if path.is_file() else sorted(path.rglob("*.py"))
    if not sources:
        return
    subprocess.run(
        [py, "-m", "compileall", "-q", "-b", "-f", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    kept = 0
    for src in sources:
        if src.with_suffix(".pyc").is_file():
            src.unlink(missing_ok=True)
        else:
            kept += 1
    if path.is_file():
        for cached in path.parent.glob(f"__pycache__/{path.stem}.*.pyc"):
            cached.unlink(missing_ok=True)
    else:
        for cache in sorted(path.rglob("__pycache__"), reverse=True):
            shutil.rmtree(cache, ignore_errors=True)
    note = f" ({kept} kept: compile failed)" if kept else ""
    print(f"[cbrun] sourceless {_digest(path.name)[:8]}{note}", flush=True)


def _sourceless_pass() -> None:
    """Strip source from banned modules that must stay importable."""
    for py, path in banned_python_artefacts():
        _sourceless(py, path)


def main() -> int:
    if not BAN:
        return 0
    for py in _pythons():
        names = _run_json(
            [
                py,
                "-c",
                "import importlib.metadata as m, json; "
                "print(json.dumps([d.metadata['Name'] for d in m.distributions() "
                "if d.metadata.get('Name')]))",
            ]
        )
        mapping = _run_json(
            [
                py,
                "-c",
                "import importlib.metadata as m, json; "
                "print(json.dumps({k: list(v) for k, v in m.packages_distributions().items()}))",
            ]
        )
        to_remove: set[str] = set()
        if isinstance(names, list):
            for dist in names:
                if _banned(str(dist)):
                    to_remove.add(str(dist))
        if isinstance(mapping, dict):
            for pkg, dists in mapping.items():
                if _banned(str(pkg)):
                    to_remove.update(str(x) for x in (dists or []))
                for dist in dists or []:
                    if _banned(str(dist)):
                        to_remove.add(str(dist))
        if to_remove:
            _uninstall(py, sorted(to_remove))
            print(f"[cbrun] stripped {len(to_remove)} dist(s)", flush=True)
        sites = _run_json(
            [
                py,
                "-c",
                "import json, site; "
                "print(json.dumps(list(site.getsitepackages()) + [site.getusersitepackages()]))",
            ]
        )
        if isinstance(sites, list):
            for site_dir in sites:
                _scan_dir(Path(str(site_dir)))

    extra = os.environ.get("CBRUN_STRIP_SCAN_DIRS", "")
    scan_roots = [
        Path("/opt/conda/bin"),
        Path("/usr/local/bin"),
        Path("/opt/conda/conda-meta"),
        Path("/usr/include"),
        Path("/usr/local/include"),
        Path("/usr/local/lib/node_modules"),
        Path("/opt/nodejs/lib/node_modules"),
        Path("/usr/lib"),
        Path("/usr/local/lib"),
        Path("/usr/lib/x86_64-linux-gnu"),
    ]
    for raw in extra.split(":"):
        if raw.strip():
            scan_roots.append(Path(raw.strip()))
    for root in scan_roots:
        _scan_dir(root)

    _sourceless_pass()

    npm = shutil.which("npm")
    if npm:
        data = _run_json([npm, "ls", "-g", "--depth=0", "--json"])
        deps = data.get("dependencies") if isinstance(data, dict) else None
        if isinstance(deps, dict):
            for name in deps:
                if _banned(str(name)):
                    subprocess.run(
                        [npm, "uninstall", "-g", str(name)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

_SCRIPT_IMPORTS = """\
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
"""

_STRIP_SCRIPT = (
    '#!/usr/bin/env python3\n'
    '"""Remove image artefacts whose names hash to the denylist set."""\n'
    + _SCRIPT_IMPORTS
    + _DISCOVERY_LIB
    + _STRIP_MAIN
)

# Loaded by every interpreter in the agent image (imported at the end of the
# stdlib ``encodings`` package, which even ``python -S -I`` reads from disk).
# While the access monitor's socket exists, it reports each open of a path with
# a component that hashes into the ban set, with the opener's pid and argv.
_ACCESS_HOOK = r'''"""cbrun: report opens of denylisted files to the access monitor."""
import sys

_SOCK = "/run/cbrun-access/hook.sock"
_HASHES = "/opt/cbrun/denylist.hashes"
_OK = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")


def _install():
    import os

    if getattr(sys, "_cbrun_access_hook", False) or not os.path.exists(_SOCK):
        return
    try:
        # builtins.open and codecs are not set up this early in startup.
        fd = os.open(_HASHES, os.O_RDONLY)
        try:
            ban = frozenset(os.read(fd, 1 << 20).decode("ascii").split())
        finally:
            os.close(fd)
    except OSError:
        return
    if not ban:
        return
    import _thread

    def norm(text):
        text = text.split("[", 1)[0].split("@", 1)[0]
        out = []
        dash = False
        for ch in text:
            if ch in _OK:
                out.append(ch)
                dash = False
            elif not dash:
                out.append("-")
                dash = True
        return "".join(out).replace("_", "-").replace(".", "-")

    sha = []

    def hashed(text):
        # Extension modules cannot load this early in startup; import on first use.
        if not sha:
            try:
                from _sha2 import sha256
            except ImportError:
                from hashlib import sha256
            sha.append(sha256)
        return sha[0](text.encode("utf-8", "surrogateescape")).hexdigest() in ban

    cache = {}

    def banned(part):
        hit = cache.get(part)
        if hit is None:
            low = part.strip().lower()
            hit = False
            for cand in {low, low.split(".", 1)[0]}:
                if cand and (hashed(cand) or hashed(norm(cand))):
                    hit = True
                    break
            if len(cache) < 100000:
                cache[part] = hit
        return hit

    here = __file__

    def importer():
        # The code that caused the open, above the import machinery and this hook.
        frame = sys._getframe(1)
        while frame is not None:
            name = frame.f_code.co_filename
            if not (
                name == here
                or name.startswith("<frozen ")
                or name.endswith(("/importlib/__init__.py", "/importlib/util.py"))
            ):
                return name
            frame = frame.f_back
        return None

    def report(path):
        import json
        import socket

        main = sys.modules.get("__main__")
        spec = getattr(main, "__spec__", None)
        origin = getattr(spec, "origin", None) or getattr(main, "__file__", None)
        argv = list(getattr(sys, "orig_argv", None) or sys.argv)
        msg = json.dumps(
            {
                "pid": os.getpid(),
                "path": path,
                "argv": [str(a)[:2048] for a in argv[:64]],
                "main": origin if isinstance(origin, str) else None,
                "importer": importer(),
            }
        ).encode("utf-8", "surrogateescape")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.settimeout(5.0)
            sock.sendto(msg, _SOCK)
        finally:
            sock.close()

    busy = set()

    def hook(event, args):
        if event != "open" or not args:
            return
        tid = _thread.get_ident()
        if tid in busy:
            return
        busy.add(tid)
        try:
            raw = args[0]
            if isinstance(raw, int):
                return
            path = os.fsdecode(os.fspath(raw))
            if not any(banned(p) for p in path.split("/") if p):
                return
            path = os.path.abspath(path)
            if path == "/app" or path.startswith("/app/"):
                return
            report(path)
        except Exception:
            pass
        finally:
            busy.discard(tid)

    sys.addaudithook(hook)
    sys._cbrun_access_hook = True


try:
    _install()
except Exception:
    pass
'''

_ACCESS_MONITOR_MAIN = r'''
import ctypes
import errno
import select
import signal
import socket
import struct
import time

SOCK_DIR = "/run/cbrun-access"
SOCK_PATH = SOCK_DIR + "/hook.sock"
HOOK_SRC = "/opt/cbrun/cbrun_access_hook.py"
HOOK_MODULE = "cbrun_access_hook.py"
MONITOR_SELF = "/opt/cbrun/access_monitor.py"
IMAGE_DISTS = "/opt/cbrun/image_dists.json"
LOADER = os.path.join("encodings", "__init__.py")
LOADER_MARKER = "# cbrun access hook"
LOADER_LINES = (
    "\n" + LOADER_MARKER + "\n"
    "try:\n"
    "    import cbrun_access_hook\n"
    "except Exception:\n"
    "    pass\n"
)
HEARTBEAT_SEC = 1.0

IN_OPEN = 0x00000020
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVE_SELF = 0x00000800
IN_DELETE_SELF = 0x00000400
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_DONT_FOLLOW = 0x02000000
IN_NONBLOCK = 0o4000
IN_CLOEXEC = 0o2000000
GUARD_MASK = IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_MOVE_SELF | IN_DELETE_SELF


def _artefact_name(path: Path) -> str | None:
    """Module name of a banned artefact, source or not."""
    if path.is_symlink():
        return None
    if path.is_dir():
        return path.name
    if path.suffix in (".py", ".pyc", ".so"):
        return path.name.split(".", 1)[0]
    return None


def _in_workspace(path: str) -> bool:
    return path == WORKSPACE or path.startswith(WORKSPACE + "/")


_SITE_NAMES = ("site-packages", "dist-packages")
_LOCAL_DISTS: dict[str, tuple[int, set[str]]] = {}


def _dist_identity(info: str) -> str | None:
    """A distribution's install identity: its RECORD, so a reinstall changes it."""
    try:
        st = os.stat(os.path.join(info, "RECORD"))
    except OSError:
        return None
    return f"{os.path.realpath(info)}:{st.st_ino}:{st.st_size}:{st.st_mtime_ns}"


def _local_url_dists() -> list[str]:
    """Every installed distribution whose recorded origin is a local path."""
    found: list[str] = []
    for site_root in _site_roots():
        for info in sorted(glob.glob(os.path.join(site_root, "*.dist-info"))):
            try:
                with open(os.path.join(info, "direct_url.json"), encoding="utf-8") as fh:
                    url = str(json.load(fh).get("url") or "")
            except (OSError, ValueError, AttributeError):
                continue
            ident = _dist_identity(info) if url.startswith("file:") else None
            if ident:
                found.append(ident)
    return found


def _site_roots() -> list[str]:
    roots: dict[str, None] = {}
    for py in _all_pythons():
        info = _python_layout(py) or {}
        for site_root in info.get("sites") or []:
            if os.path.isdir(str(site_root)):
                roots[os.path.realpath(str(site_root))] = None
    return list(roots)


def _image_dists() -> frozenset[str]:
    """Local-path distributions the image already had before any solve started.

    Package builders (conda among them) record their own build directory as a
    ``file:`` origin, so that origin alone does not mark the agent's code. What
    the agent installs from a local path appears only after this snapshot.
    """
    with open(IMAGE_DISTS, encoding="utf-8") as fh:
        return frozenset(json.load(fh))


def _locally_installed(site_root: str) -> set[str]:
    """Top-level names of distributions the agent installed from a local path (e.g. ``pip install .``)."""
    try:
        stamp = os.stat(site_root).st_mtime_ns
    except OSError:
        return set()
    cached = _LOCAL_DISTS.get(site_root)
    if cached and cached[0] == stamp:
        return cached[1]
    baseline = _image_dists()
    names: set[str] = set()
    for info in glob.glob(os.path.join(site_root, "*.dist-info")):
        try:
            with open(os.path.join(info, "direct_url.json"), encoding="utf-8") as fh:
                url = str(json.load(fh).get("url") or "")
        except (OSError, ValueError, AttributeError):
            continue
        if not url.startswith("file:") or _dist_identity(info) in baseline:
            continue
        try:
            with open(os.path.join(info, "RECORD"), encoding="utf-8") as fh:
                for line in fh:
                    top = line.split(",", 1)[0].split("/", 1)[0]
                    if top and not top.startswith(".."):
                        names.add(top.split(".", 1)[0] if top.endswith((".py", ".pth")) else top)
        except OSError:
            continue
    _LOCAL_DISTS[site_root] = (stamp, names)
    return names


def toolchain_code(path: str | None, stdlibs: list[str]) -> bool:
    """True for stdlib or installed-package code, not the agent's own."""
    if not path or not path.startswith("/"):
        return False
    real = os.path.realpath(path)
    if _in_workspace(real) or _in_workspace(path):
        return False
    if any(real.startswith(root + "/") for root in stdlibs):
        parts = Path(real).parts
        if not any(p in _SITE_NAMES for p in parts):
            return True
    parts = Path(real).parts
    for i, part in enumerate(parts):
        if part in _SITE_NAMES and i + 1 < len(parts):
            top = parts[i + 1]
            top = top.split(".", 1)[0] if top.endswith(".py") else top
            return top not in _locally_installed(str(Path(*parts[: i + 1])))
    return False


def toolchain_entry(main: str | None, stdlibs: list[str]) -> bool:
    """True when the process runs a tool: a bin-dir script or installed package code."""
    if not main or not main.startswith("/"):
        return False
    if os.path.basename(os.path.dirname(main)) == "bin" and not _in_workspace(main):
        return True
    return toolchain_code(main, stdlibs)


def protected_files() -> list[str]:
    """Regular files under every banned artefact, outside the workspace."""
    roots: list[Path] = [p for _py, p in banned_python_artefacts(_artefact_name)]
    roots.extend(banned_node_artefacts())
    found: dict[str, None] = {}
    for root in roots:
        real = os.path.realpath(root)
        # License copies in dist metadata are not the implementation.
        if _in_workspace(real) or any(p.endswith(".dist-info") for p in Path(real).parts):
            continue
        if os.path.isfile(real):
            found[real] = None
            continue
        for dirpath, dirnames, files in os.walk(real):
            dirnames[:] = [d for d in dirnames if not d.endswith(".dist-info")]
            for name in files:
                path = os.path.join(dirpath, name)
                if os.path.isfile(path) and not os.path.islink(path):
                    found[path] = None
    return sorted(found)


def _stdlib_dirs() -> list[str]:
    dirs: dict[str, None] = {}
    for py in _all_pythons():
        info = _python_layout(py)
        if info and info.get("stdlib"):
            dirs[os.path.realpath(str(info["stdlib"]))] = None
    return list(dirs)


def install_hooks() -> int:
    """Make every interpreter load the attribution hook, venvs included.

    ``.pth`` files and ``sitecustomize`` do not reach venvs or pip's isolated
    build environments, and ``site`` is frozen since 3.11. The stdlib
    ``encodings`` package is read from disk by every interpreter, even under
    ``-S`` and ``-I``, so the hook is imported from the end of it.
    """
    os.chmod(HOOK_SRC, 0o644)
    count = 0
    for stdlib in _stdlib_dirs():
        link = os.path.join(stdlib, HOOK_MODULE)
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(HOOK_SRC, link)
        loader = os.path.join(stdlib, LOADER)
        text = Path(loader).read_text(encoding="utf-8")
        if LOADER_MARKER not in text:
            with open(loader, "a", encoding="utf-8") as fh:
                fh.write(LOADER_LINES)
        count += 1
    with open(IMAGE_DISTS, "w", encoding="utf-8") as fh:
        json.dump(_local_url_dists(), fh)
    os.chmod(IMAGE_DISTS, 0o644)
    print(f"[cbrun] access hook installed for {count} stdlib dir(s)", flush=True)
    return 0 if count else 1


def guarded_files() -> list[str]:
    """Files whose change would disable attribution or monitoring."""
    paths = [HOOK_SRC, MONITOR_SELF, str(HASHES), IMAGE_DISTS]
    for stdlib in _stdlib_dirs():
        link = os.path.join(stdlib, HOOK_MODULE)
        loader = os.path.join(stdlib, LOADER)
        if os.path.realpath(link) != HOOK_SRC:
            raise RuntimeError(f"access hook link missing in {stdlib}")
        if LOADER_MARKER not in Path(loader).read_text(encoding="utf-8"):
            raise RuntimeError(f"access hook not loaded by {loader}")
        paths += [link, loader]
    return paths


def _fingerprint(path: str):
    try:
        st = os.lstat(path)
    except OSError:
        return None
    target = os.readlink(path) if os.path.islink(path) else None
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode, target)


def _emit(**event) -> None:
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _cmdline(pid: int) -> list[str] | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if not raw:
        return None
    return [a.decode("utf-8", "replace") for a in raw.rstrip(b"\0").split(b"\0")]


def _parent_exe(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            stat = fh.read().decode("utf-8", "replace")
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        return os.readlink(f"/proc/{ppid}/exe")
    except (OSError, ValueError, IndexError):
        return None


class Inotify:
    def __init__(self) -> None:
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.fd = self.libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")

    def watch(self, path: str, mask: int) -> int:
        wd = self.libc.inotify_add_watch(self.fd, os.fsencode(path), mask)
        if wd < 0:
            err = ctypes.get_errno()
            raise OSError(err, f"inotify_add_watch {path}: {os.strerror(err)}")
        return wd

    def read(self):
        try:
            buf = os.read(self.fd, 1 << 16)
        except BlockingIOError:
            return
        i = 0
        while i + 16 <= len(buf):
            wd, mask, _cookie, length = struct.unpack_from("iIII", buf, i)
            i += 16 + length
            yield wd, mask


def _recv_reports(sock: socket.socket):
    while True:
        try:
            data, anc, _flags, _addr = sock.recvmsg(1 << 17, socket.CMSG_SPACE(12))
        except (BlockingIOError, InterruptedError):
            return
        cred_pid = None
        for level, kind, payload in anc:
            if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                cred_pid = struct.unpack("iII", payload[:12])[0]
        yield data, cred_pid


def monitor() -> int:
    if not BAN:
        _emit(t="error", detail=f"no denylist hashes at {HASHES}")
        return 2
    try:
        guarded = guarded_files()
        stdlibs = _stdlib_dirs()
        protected = protected_files()
        inotify = Inotify()
        by_wd: dict[int, int] = {}
        for index, path in enumerate(protected):
            by_wd.setdefault(inotify.watch(path, IN_OPEN | IN_DELETE_SELF | IN_MOVE_SELF), index)
        index_of = {path: i for i, path in enumerate(protected)}
        inode_of = {}
        for i, path in enumerate(protected):
            st = os.stat(path)
            inode_of.setdefault((st.st_dev, st.st_ino), i)
        os.makedirs(SOCK_DIR, exist_ok=True)
        os.chmod(SOCK_DIR, 0o755)
        if os.path.lexists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(SOCK_PATH)
        os.chmod(SOCK_PATH, 0o666)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 22)
        sock.setblocking(False)
        guarded.append(SOCK_PATH)
        guard_wd: dict[int, str] = {}
        for path in guarded:
            flags = GUARD_MASK | (IN_DONT_FOLLOW if os.path.islink(path) else 0)
            guard_wd[inotify.watch(path, flags)] = path
        prints = {path: _fingerprint(path) for path in guarded}
    except Exception as exc:  # noqa: BLE001
        _emit(t="error", detail=f"{type(exc).__name__}: {exc}")
        return 2

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    start = time.monotonic()
    _emit(t="ready", pid=os.getpid(), protected=protected, guarded=guarded)

    def resolve(path: str) -> int | None:
        hit = index_of.get(os.path.realpath(path))
        if hit is not None:
            return hit
        try:
            st = os.stat(path)
        except OSError:
            return None
        return inode_of.get((st.st_dev, st.st_ino))

    def drain_reports() -> None:
        for data, cred_pid in _recv_reports(sock):
            ts = round(time.monotonic() - start, 3)
            try:
                report = json.loads(data.decode("utf-8", "surrogateescape"))
                claimed = int(report.get("pid"))
            except (ValueError, TypeError, AttributeError):
                _emit(t="forged", ts=ts, pid=cred_pid, detail="malformed hook report")
                continue
            if cred_pid is None or claimed != cred_pid:
                _emit(t="forged", ts=ts, pid=cred_pid,
                      detail=f"hook report claims pid {claimed}, sender is pid {cred_pid}")
                continue
            index = resolve(str(report.get("path") or ""))
            if index is None:
                continue
            argv = _cmdline(cred_pid)
            source = "proc"
            if argv is None:
                argv = [str(a) for a in (report.get("argv") or [])]
                source = "hook"
            main = report.get("main") if isinstance(report.get("main"), str) else None
            importer = report.get("importer") if isinstance(report.get("importer"), str) else None
            _emit(t="attr", ts=ts, f=index, pid=cred_pid, argv=argv, argv_source=source,
                  main=main, importer=importer, parent_exe=_parent_exe(cred_pid),
                  tool_entry=toolchain_entry(main, stdlibs),
                  tool_importer=toolchain_code(importer, stdlibs))

    last_beat = 0.0
    while True:
        try:
            ready, _, _ = select.select([sock, inotify.fd, sys.stdin], [], [], HEARTBEAT_SEC / 2)
        except InterruptedError:
            continue
        # Hook reports are sent before the open, so read them first.
        drain_reports()
        for wd, mask in inotify.read():
            ts = round(time.monotonic() - start, 3)
            if mask & IN_Q_OVERFLOW:
                _emit(t="overflow", ts=ts)
            elif wd in guard_wd:
                if not mask & IN_IGNORED:
                    _emit(t="tamper", ts=ts, path=guard_wd[wd], detail=f"changed (mask {mask:#x})")
            elif wd in by_wd:
                if mask & IN_OPEN:
                    _emit(t="open", ts=ts, f=by_wd[wd])
                if mask & (IN_DELETE_SELF | IN_MOVE_SELF):
                    _emit(t="tamper", ts=ts, path=protected[by_wd[wd]], detail="protected file removed or moved")
        drain_reports()
        if sys.stdin in ready and not os.read(sys.stdin.fileno(), 4096):
            _emit(t="bye", ts=round(time.monotonic() - start, 3))
            return 0
        now = time.monotonic()
        if now - last_beat >= HEARTBEAT_SEC:
            last_beat = now
            ts = round(now - start, 3)
            for path, before in prints.items():
                after = _fingerprint(path)
                if after != before:
                    prints[path] = after
                    _emit(t="tamper", ts=ts, path=path,
                          detail="removed" if after is None else "changed")
            _emit(t="hb", ts=ts)


if __name__ == "__main__":
    if sys.argv[1:] == ["--install-hooks"]:
        sys.exit(install_hooks())
    if sys.argv[1:] == ["--list"]:
        print(json.dumps({"protected": protected_files(), "guarded": guarded_files()}))
        sys.exit(0)
    try:
        sys.exit(monitor())
    except BrokenPipeError:
        sys.exit(0)
'''

_ACCESS_MONITOR = (
    '#!/usr/bin/env python3\n'
    '"""cbrun access monitor: report every open of a denylisted file."""\n'
    + _SCRIPT_IMPORTS
    + _DISCOVERY_LIB
    + _ACCESS_MONITOR_MAIN
)

_PIP_MODULE_HOOK = r'''"""Block ``python -m pip`` installs that hash to the denylist set."""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

_HASHES = Path(os.environ.get("CBRUN_DENYLIST_HASHES", "/opt/cbrun/denylist.hashes"))
_CMDS = {"install", "i", "add", "download", "wheel"}


def _norm(name: str) -> str:
    text = name.strip().lower().split("[", 1)[0].split("@", 1)[0]
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.replace("_", "-").replace(".", "-")


def check_orig_argv(argv=None, hashes_path=None) -> None:
    path = Path(hashes_path) if hashes_path else _HASHES
    if not path.is_file():
        return
    ban = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}
    if not ban:
        return
    args = list(argv if argv is not None else getattr(sys, "orig_argv", sys.argv))
    try:
        idx = args.index("-m")
    except ValueError:
        return
    if idx + 1 >= len(args) or args[idx + 1] != "pip":
        return
    rest = args[idx + 2 :]
    i = 0
    names: list[str] = []
    while i < len(rest):
        tok = rest[i]
        if tok in _CMDS:
            i += 1
            while i < len(rest):
                arg = rest[i]
                if arg.startswith("-"):
                    if arg in ("-r", "--requirement") and i + 1 < len(rest):
                        req = Path(rest[i + 1])
                        if req.is_file():
                            for line in req.read_text(encoding="utf-8").splitlines():
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    names.append(line.split(";", 1)[0].strip())
                        i += 2
                        continue
                    i += 1
                    continue
                names.append(arg)
                i += 1
            break
        i += 1
    for name in names:
        digest = hashlib.sha256(_norm(name).encode()).hexdigest()
        if digest in ban:
            print(
                f"[cbrun denylist] blocked install of upstream package: {name}",
                file=sys.stderr,
            )
            print(
                "[cbrun denylist] implement this functionality yourself; "
                "do not reuse the upstream product.",
                file=sys.stderr,
            )
            raise SystemExit(1)


check_orig_argv()
'''


def render_pip_shim() -> str:
    return _PIP_SHIM


def render_conda_shim() -> str:
    return _CONDA_SHIM


def render_npm_shim() -> str:
    return _NPM_SHIM


def render_strip_script() -> str:
    return _STRIP_SCRIPT


def render_pip_module_hook() -> str:
    return _PIP_MODULE_HOOK


def render_access_monitor() -> str:
    return _ACCESS_MONITOR


def render_access_hook() -> str:
    return _ACCESS_HOOK


def write_shim_assets(
    build_ctx: Path,
    denylist_path: Path,
    *,
    required: bool = False,
) -> str:
    """Copy hash denylist + shim scripts into Docker build context; return Dockerfile snippet."""
    if not denylist_path.is_file():
        if required:
            raise MissingDenylist(
                f"source/denylist.json is missing at {denylist_path}. "
                "Every released case tracks this file; restore it from git, "
                "or pass --no-enforce-denylist to skip the scan."
            )
        return ""
    hashes = install_ban_hashes_from_file(denylist_path)
    if not hashes:
        return ""

    build_ctx.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("denylist.hashes", "\n".join(hashes) + "\n"),
        ("strip_banned.py", render_strip_script()),
        ("cbrun_denylist_hook.py", render_pip_module_hook()),
        ("access_monitor.py", render_access_monitor()),
        ("cbrun_access_hook.py", render_access_hook()),
    ):
        path = build_ctx / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)
    shim_dir = build_ctx / "shims"
    shim_dir.mkdir(exist_ok=True)
    pip_shim = render_pip_shim()
    conda_shim = render_conda_shim()
    npm_shim = render_npm_shim()
    for name, content in (
        ("pip", pip_shim),
        ("pip3", pip_shim),
        ("conda", conda_shim),
        ("mamba", conda_shim),
        ("uv", pip_shim),
        ("npm", npm_shim),
        ("npx", npm_shim),
        ("pnpm", npm_shim),
        ("yarn", npm_shim),
    ):
        dest = shim_dir / name
        dest.write_text(content, encoding="utf-8")
        dest.chmod(0o755)
    bins = " ".join(
        f"{SHIM_BIN_DIR}/{name}"
        for name in ("pip", "pip3", "conda", "mamba", "uv", "npm", "npx", "pnpm", "yarn")
    )
    return (
        f"COPY denylist.hashes {CONTAINER_DENYLIST_HASHES_PATH}\n"
        f"COPY strip_banned.py {CONTAINER_STRIP_SCRIPT_PATH}\n"
        f"COPY cbrun_denylist_hook.py {CONTAINER_PIP_HOOK_PATH}\n"
        f"COPY access_monitor.py {CONTAINER_ACCESS_MONITOR_PATH}\n"
        f"COPY cbrun_access_hook.py {CONTAINER_ACCESS_HOOK_PATH}\n"
        f"COPY shims/ {SHIM_BIN_DIR}/\n"
        f"RUN chmod +x {bins} && "
        f"chmod 644 {CONTAINER_DENYLIST_HASHES_PATH} {CONTAINER_STRIP_SCRIPT_PATH} {CONTAINER_PIP_HOOK_PATH} "
        f"{CONTAINER_ACCESS_MONITOR_PATH} {CONTAINER_ACCESS_HOOK_PATH} && "
        f"python3 {CONTAINER_STRIP_SCRIPT_PATH} && "
        f"python3 {CONTAINER_ACCESS_MONITOR_PATH} --install-hooks && "
        "for py in /opt/conda/bin/python3 /usr/bin/python3; do "
        '  if [ -x "$py" ]; then '
        '    dest="$($py -c \'import site; print(site.getsitepackages()[0])\')" && '
        f'    ln -sfn {CONTAINER_PIP_HOOK_PATH} "$dest/cbrun_denylist_hook.py" && '
        '    printf \'import cbrun_denylist_hook\\n\' > "$dest/zz_cbrun_denylist.pth"; '
        "  fi; "
        "done && "
        f'printf "export PATH={SHIM_BIN_DIR}:\\$PATH\\n" > /etc/profile.d/00-cbrun-denylist.sh\n'
        f"ENV PATH={SHIM_BIN_DIR}:$PATH\n"
    )


def import_root_from_ban_token(token: str) -> str | None:
    """Normalize one ``import_ban`` token to the top-level import root."""
    text = str(token).strip().rstrip("/")
    if not text:
        return None
    if text.startswith("@") and "/" in text:
        parts = [p for p in text.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return None
    if "/" in text:
        last = text.rsplit("/", 1)[-1].strip()
        return last or None
    if "." in text:
        first = text.split(".", 1)[0].strip()
        return first or None
    return text


def import_roots_from_ban_tokens(tokens: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    roots: list[str] = []
    for token in tokens:
        root = import_root_from_ban_token(token)
        if root is None or root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


def _stdlib_roots() -> set[str]:
    import sys

    names = getattr(sys, "stdlib_module_names", None)
    return set(names) if names else set()


def _parse_probe_rows(output: str, roots: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or "\t" not in line:
            continue
        name, origin = line.split("\t", 1)
        if name in roots:
            found[name] = origin.strip()
    return found


@dataclass
class RuntimeEquivalent:
    import_root: str
    runtime: str
    evidence: str = ""


@dataclass
class ProbeSpec:
    python_roots: list[str] = field(default_factory=list)
    node_roots: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    runtime_equivalents: list[RuntimeEquivalent] = field(default_factory=list)


def probe_spec_from_payload(payload: dict) -> ProbeSpec:
    tokens = [str(x).strip() for x in (payload.get("import_ban") or []) if str(x).strip()]
    install = [str(x).strip() for x in (payload.get("install_ban") or []) if str(x).strip()]
    raw_roots = import_roots_from_ban_tokens(tokens)
    python_roots = [r for r in raw_roots if is_probeable_import_root(r)]
    node_roots = [
        r for r in raw_roots if is_probeable_import_root(r) or (r.startswith("@") and "/" in r)
    ]
    commands = []
    seen_cmd: set[str] = set()
    for tok in tokens + install:
        cmd = tok.strip().rstrip("/")
        if is_command_like_token(tok) and cmd not in seen_cmd:
            seen_cmd.add(cmd)
            commands.append(cmd)
    headers: list[str] = []
    seen_hdr: set[str] = set()
    for tok in tokens + install:
        base = Path(tok.strip().rstrip("/")).name
        if any(base.endswith(suf) for suf in (".h", ".hh", ".hpp", ".hxx")) and base not in seen_hdr:
            seen_hdr.add(base)
            headers.append(base)
    equivalents: list[RuntimeEquivalent] = []
    for row in payload.get("runtime_equivalents") or []:
        if not isinstance(row, dict):
            continue
        root = str(row.get("import_root") or "").strip()
        runtime = str(row.get("runtime") or "").strip()
        if not root or runtime not in _RUNTIME_FAMILIES:
            continue
        equivalents.append(
            RuntimeEquivalent(
                import_root=root,
                runtime=runtime,
                evidence=str(row.get("evidence") or "").strip(),
            )
        )
    return ProbeSpec(
        python_roots=python_roots,
        node_roots=node_roots,
        commands=commands,
        headers=headers,
        runtime_equivalents=equivalents,
    )


def _unified_probe_command(spec: ProbeSpec) -> str:
    blob = json.dumps(
        {
            "python_roots": spec.python_roots,
            "node_roots": spec.node_roots,
            "commands": spec.commands,
            "headers": spec.headers,
            "node_equiv": [
                row.import_root
                for row in spec.runtime_equivalents
                if row.runtime == "node"
            ],
        }
    )
    return (
        "python3 - <<'PY'\n"
        "import importlib.util, json, os, shutil, subprocess, sys\n"
        f"spec = json.loads({json.dumps(blob)})\n"
        "def pythons():\n"
        "    seen = set()\n"
        "    for p in ('/opt/conda/bin/python3', '/usr/bin/python3', shutil.which('python3') or ''):\n"
        "        if p and os.path.isfile(p) and p not in seen:\n"
        "            seen.add(p)\n"
        "            yield p\n"
        "for py in list(pythons()) or [sys.executable]:\n"
        "    code = (\n"
        "        'import importlib.util, json, sys\\n'\n"
        "        'roots = json.loads(sys.argv[1])\\n'\n"
        "        'std = set(getattr(sys, \"stdlib_module_names\", ()) )\\n'\n"
        "        'for root in roots:\\n'\n"
        "        '    if root in std:\\n'\n"
        "        '        print(root + \"\\\\t__STDLIB__\")\\n'\n"
        "        '        continue\\n'\n"
        "        '    try:\\n'\n"
        "        '        found = importlib.util.find_spec(root)\\n'\n"
        "        '    except (ModuleNotFoundError, ValueError):\\n'\n"
        "        '        print(root + \"\\\\t__ABSENT__\")\\n'\n"
        "        '        continue\\n'\n"
        "        '    if found is None:\\n'\n"
        "        '        print(root + \"\\\\t__ABSENT__\")\\n'\n"
        "        '        continue\\n'\n"
        "        '    origin = found.origin or \"\"\\n'\n"
        "        '    if origin:\\n'\n"
        "        '        print(root + \"\\\\t\" + origin)\\n'\n"
        "        '        continue\\n'\n"
        "        '    locs = list(found.submodule_search_locations or [])\\n'\n"
        "        '    print(root + \"\\\\t\" + (locs[0] if locs else \"__PRESENT__\"))\\n'\n"
        "    )\n"
        "    try:\n"
        "        out = subprocess.check_output([py, '-c', code, json.dumps(spec['python_roots'])], text=True)\n"
        "    except Exception as exc:\n"
        "        print('pyerr\\t' + py + '\\t' + str(exc))\n"
        "        continue\n"
        "    sys.stdout.write(out)\n"
        "if shutil.which('node') and spec['node_roots']:\n"
        "    for root in spec['node_roots']:\n"
        "        try:\n"
        "            loc = subprocess.check_output(\n"
        "                ['node', '-e', 'try { console.log(require.resolve(process.argv[1])) } '\n"
        "                 'catch (e) { console.log(\"__ABSENT__\") }', root],\n"
        "                text=True, stderr=subprocess.DEVNULL,\n"
        "            ).strip()\n"
        "        except Exception:\n"
        "            loc = '__ABSENT__'\n"
        "        print('node\\t' + root + '\\t' + loc)\n"
        "        for base in ('/usr/local/lib/node_modules', '/opt/nodejs/lib/node_modules'):\n"
        "            path = os.path.join(base, root)\n"
        "            print('nmdir\\t' + root + '\\t' + ('PRESENT' if os.path.exists(path) else 'ABSENT'))\n"
        "for name in spec['commands']:\n"
        "    print('cmd\\t' + name + '\\t' + (shutil.which(name) or '__ABSENT__'))\n"
        "for hdr in spec['headers']:\n"
        "    hits = [p for p in ('/usr/include/' + hdr, '/usr/local/include/' + hdr) if os.path.exists(p)]\n"
        "    print('hdr\\t' + hdr + '\\t' + (hits[0] if hits else '__ABSENT__'))\n"
        "    libhits = []\n"
        "    stem = hdr.rsplit('.', 1)[0]\n"
        "    for libdir in ('/usr/lib', '/usr/local/lib', '/usr/lib/x86_64-linux-gnu'):\n"
        "        for fn in ('lib' + stem + '.so', 'lib' + stem + '.a'):\n"
        "            p = os.path.join(libdir, fn)\n"
        "            if os.path.exists(p):\n"
        "                libhits.append(p)\n"
        "    print('lib\\t' + stem + '\\t' + (libhits[0] if libhits else '__ABSENT__'))\n"
        "print('warm\\t/opt/cb-warm\\t' + ('PRESENT' if os.path.exists('/opt/cb-warm') else 'ABSENT'))\n"
        "print('repo\\t/opt/codingbench/repo\\t' + ('PRESENT' if os.path.exists('/opt/codingbench/repo') else 'ABSENT'))\n"
        "nodes = []\n"
        "for p in ('/opt/cbrun/runtime/node/bin/node', shutil.which('node') or ''):\n"
        "    if p and os.path.isfile(p) and p not in nodes:\n"
        "        nodes.append(p)\n"
        "for name in spec.get('node_equiv') or []:\n"
        "    for node in nodes:\n"
        "        try:\n"
        "            ver = subprocess.check_output(\n"
        "                [node, '-p', 'process.versions[' + json.dumps(name) + ']||\"\"'],\n"
        "                text=True,\n"
        "            ).strip()\n"
        "        except Exception:\n"
        "            ver = ''\n"
        "        print('rtver\\t' + name + '\\t' + (ver or 'ABSENT') + '\\t' + node)\n"
        "PY"
    )


@dataclass
class ImportProbeResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _record_present(result: ImportProbeResult, tag: str, kind: str, name: str, origin: str) -> None:
    if origin in {"", "__ABSENT__", "__STDLIB__", "ABSENT"}:
        return
    result.errors.append(
        f"banned {kind} {name!r} is present in {tag} (origin={origin})"
    )


def probe_banned_imports(
    tag: str,
    denylist_path: Path | str,
    *,
    runner=None,
) -> ImportProbeResult:
    """Probe whether banned roots, binaries, or leftovers resolve in *tag*."""
    result = ImportProbeResult()
    path = Path(denylist_path)
    if not path.is_file():
        return result
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"denylist unreadable: {path}: {exc}")
        return result
    if not isinstance(payload, dict):
        result.errors.append(f"denylist is not an object: {path}")
        return result
    spec = probe_spec_from_payload(payload)
    command = _unified_probe_command(spec)
    if runner is None:
        from .docker_env import Container

        container = Container.start(tag, network="none")
        try:
            outcome = container.exec(command, timeout_sec=60.0)
        finally:
            container.remove()
    else:
        outcome = runner(command)
    tail = getattr(outcome, "tail", "") or ""
    roots = list(spec.python_roots)
    found = _parse_probe_rows(tail, roots)
    for root, origin in found.items():
        if origin and origin not in {"__ABSENT__", "__STDLIB__"}:
            result.errors.append(
                f"banned import root {root!r} is importable in {tag} (origin={origin})"
            )
    for raw in tail.splitlines():
        parts = raw.strip().split("\t")
        if not parts:
            continue
        kind = parts[0]
        if kind == "node" and len(parts) >= 3:
            _record_present(result, tag, "npm package", parts[1], parts[2])
        elif kind == "nmdir" and len(parts) >= 3:
            _record_present(result, tag, "npm directory", parts[1], parts[2])
        elif kind == "cmd" and len(parts) >= 3:
            _record_present(result, tag, "command", parts[1], parts[2])
        elif kind == "hdr" and len(parts) >= 3:
            _record_present(result, tag, "header", parts[1], parts[2])
        elif kind == "lib" and len(parts) >= 3:
            _record_present(result, tag, "library", parts[1], parts[2])
        elif kind == "warm" and len(parts) >= 3 and parts[2] == "PRESENT":
            result.errors.append(f"upstream leftover /opt/cb-warm is present in {tag}")
        elif kind == "repo" and len(parts) >= 3 and parts[2] == "PRESENT":
            result.errors.append(f"upstream leftover /opt/codingbench/repo is present in {tag}")
        elif kind == "rtver" and len(parts) >= 3 and parts[2] not in {"", "ABSENT"}:
            origin = parts[3] if len(parts) >= 4 else "node"
            result.warnings.append(
                f"Node runtime reports process.versions.{parts[1]}={parts[2]!r} "
                f"in {tag} ({origin})"
            )
    return result


def _login_which(tag: str, command: str, *, runner=None) -> str:
    script = (
        "bash -lc "
        + json.dumps(f"command -v {command} 2>/dev/null || true")
    )
    if runner is None:
        from .docker_env import Container

        container = Container.start(tag, network="none")
        try:
            outcome = container.exec(script, timeout_sec=30.0)
        finally:
            container.remove()
    else:
        outcome = runner(script)
    text = (getattr(outcome, "tail", "") or "").strip().splitlines()
    for line in reversed(text):
        value = line.strip()
        if value:
            return value
    return ""


def probe_agent_runtime_leak(
    agent_tag: str,
    deliverable_tag: str,
    commands: list[str],
    *,
    runner=None,
) -> ImportProbeResult:
    """Error when the agent image added a login-PATH command the deliverable lacked."""
    result = ImportProbeResult()
    for command in commands:
        name = str(command or "").strip()
        if not name:
            continue
        deliverable = _login_which(deliverable_tag, name, runner=runner)
        agent = _login_which(agent_tag, name, runner=runner)
        if agent and not deliverable:
            result.errors.append(
                f"agent image {agent_tag} exposes {name!r} on the login PATH "
                f"({agent}); deliverable {deliverable_tag} does not"
            )
    return result


def log_probe_result(probe: ImportProbeResult, *, prefix: str = "[cbrun]") -> None:
    for warning in probe.warnings:
        print(f"{prefix} denylist probe warning: {warning}", flush=True)
    for error in probe.errors:
        print(f"{prefix} denylist probe error: {error}", file=sys.stderr, flush=True)
