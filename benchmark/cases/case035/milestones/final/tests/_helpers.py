# feature: F00
"""Shared public-interface drivers; no product expectations live here.

Pass an explicit command prefix, e.g. ("velnora",) for the candidate or
("velnora",) for the reference. No alternative executable is discovered.
Environment mappings replace, rather than supplement, the child environment.
Report grammars not yet published must be supplied by the caller; this module
never infers a table, diagnostic category, or success condition from prose.
Requires Python 3.11 or later. Only the names in __all__ form the shared API.
"""

from __future__ import annotations

import configparser as _configparser
import contextlib as _contextlib
import dataclasses as _dataclasses
import email.parser as _email_parser
import email.policy as _email_policy
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import signal as _signal
import stat as _stat
import subprocess as _subprocess
import tarfile as _tarfile
import tempfile as _tempfile
import tomllib as _tomllib
import zipfile as _zipfile

__all__ = [
    "CommandResult", "Workspace", "run_cli", "isolated_workspace",
    "make_environment", "read_toml", "snapshot_toml", "parse_json", "parse_jsonl",
    "parse_report", "parse_diagnostics", "read_zip", "read_tar",
    "parse_metadata", "parse_entry_points", "snapshot_files",
    "snapshot_tree", "run_python", "probe_python", "snapshot_installed",
]


@_dataclasses.dataclass(frozen=True)
class CommandResult:
    """Return argv, status, and separate UTF-8 stdout/stderr from a completed call.

    Nonzero returncode is preserved, including negative POSIX signal statuses.
    Launch, timeout, cleanup and decoding errors raise instead of producing this
    object. Output is not stripped and line endings are not normalized.
    """

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@_dataclasses.dataclass(frozen=True)
class Workspace:
    """Return isolated directory paths, with no process status attached.

    Paths exist only inside isolated_workspace's context. Creation and removal
    errors propagate. Runtime is a storage directory, not an installed product.
    """

    root: _Path
    home: _Path
    config: _Path
    cache: _Path
    project: _Path
    runtime: _Path
    temporary: _Path


def make_environment(base, *, updates=None, remove=(), remove_prefixes=()):
    """Return a copied environment with explicit removals followed by updates.

    Pass os.environ explicitly to inherit the host, or {} for a clean mapping.
    No process runs; invalid non-string keys/values raise TypeError. No variables
    or product settings are implicitly inserted or removed.
    """
    result = {
        key: value for key, value in base.items()
        if key not in remove and not key.startswith(tuple(remove_prefixes))
    }
    if updates is not None:
        result.update(updates)
    if any(not isinstance(k, str) or not isinstance(v, str)
           for k, v in result.items()):
        raise TypeError("Environment keys and values must be strings")
    return result


@_contextlib.contextmanager
def isolated_workspace(*, parent=None):
    """Yield a Workspace of fresh directories and remove it on context exit.

    The caller binds these paths to documented environment variables using
    make_environment. This does not mutate cwd or os.environ, install anything,
    or run a process. Filesystem and cleanup errors propagate.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-", dir=parent) as directory:
        root = _Path(directory).resolve()
        paths = {name: root / name for name in
                 ("home", "config", "cache", "project", "runtime", "temporary")}
        for path in paths.values():
            path.mkdir()
        yield Workspace(root=root, **paths)


def _positive_timeout(value):
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and positive")


def run_cli(entrypoint, args=(), *, cwd, env, stdin="", timeout=60.0):
    """Return CommandResult from an explicit argv prefix plus argument sequence.

    cwd and the entire child environment are required. stdin is UTF-8 text,
    closed after delivery; an empty string supplies EOF. No shell, extra flags,
    diagnostics options or success checks are added. Business failures retain
    their exit status. Launch/encoding/I/O failures propagate. A timeout raises
    AssertionError chained from TimeoutExpired, retaining captured bytes there.
    POSIX children use a new session, killed as a group on timeout; cleanup is
    bounded to five seconds. Other platforms kill the direct child and bound
    pipe cleanup as well. This is piped input, not a terminal emulator.
    """
    _positive_timeout(timeout)
    if isinstance(entrypoint, (str, bytes, _os.PathLike)):
        raise TypeError("entrypoint must be an argv sequence, not a shell string")
    if isinstance(args, (str, bytes)):
        raise TypeError("args must be an argv sequence")
    command = tuple(_os.fspath(part) for part in (*entrypoint, *args))
    if not command:
        raise ValueError("An explicit entrypoint is required")
    child_env = make_environment(env)
    payload = stdin.encode("utf-8")
    process = _subprocess.Popen(
        command, cwd=cwd, env=child_env, stdin=_subprocess.PIPE,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
        start_new_session=(_os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(payload, timeout=timeout)
    except _subprocess.TimeoutExpired as error:
        try:
            if _os.name == "posix":
                _os.killpg(process.pid, _signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            # The process exited between timeout detection and signal delivery.
            pass
        try:
            stdout, stderr = process.communicate(timeout=5.0)
            error.output, error.stderr = stdout, stderr
        except _subprocess.TimeoutExpired as cleanup_error:
            raise AssertionError("Command timed out; pipe cleanup also timed out") from cleanup_error
        raise AssertionError(f"Command exceeded {timeout} seconds: {command!r}") from error
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    return CommandResult(command, process.returncode,
                         stdout.decode("utf-8"), stderr.decode("utf-8"))


def read_toml(path):
    """Return the complete TOML mapping; file/decode/parse errors propagate.

    No fields are selected or defaulted and no process status is interpreted.
    """
    with _Path(path).open("rb") as stream:
        return _tomllib.load(stream)


def snapshot_toml(paths):
    """Read persistent document values, retaining absence and propagating errors.

    This compares declared data when preservation of settings is promised.
    Use snapshot_files instead when a promise forbids writing the document.
    """
    result = {}
    for supplied in paths:
        path = _Path(supplied)
        try:
            result[path] = read_toml(path)
        except FileNotFoundError:
            result[path] = None
    return result


def _invalid_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def parse_json(text):
    """Return one complete JSON value; malformed or trailing data raises.

    Nonstandard NaN/Infinity values are rejected. No exit status is interpreted.
    """
    return _json.loads(text, parse_constant=_invalid_constant)


def parse_jsonl(text):
    """Return every JSONL record in order; empty input returns an empty list.

    Blank records and malformed or truncated JSON raise, rather than being
    skipped. A final newline is optional. No process status is interpreted.
    """
    return [parse_json(line) for line in text.splitlines()]


def parse_report(text, *, parser=None):
    """Return a report parsed with a caller-supplied, published grammar.

    parser(text) must return (value, consumed_character_count). Missing grammar,
    an invalid consumption count, or leftover text raises ValueError. Parser
    errors propagate. All whitespace must be consumed explicitly by the grammar;
    this wrapper never selects lines, guesses columns or interprets exit status.
    """
    if parser is None:
        raise ValueError("A published report grammar is required")
    value, consumed = parser(text)
    if type(consumed) is not int or consumed != len(text):
        raise ValueError("Report parser did not consume the complete output")
    return value


def parse_diagnostics(text, *, required_fields, allowed_values):
    """Return complete JSONL diagnostic objects under an explicit schema.

    Supply stderr directly and the published required fields and allowed values
    (field -> collection). Unknown additional fields are retained. Missing
    fields, unknown enumerated values, non-objects and parse errors raise.
    Empty text returns []; the caller checks status/diagnostic combinations.
    No success or failure categories or exit statuses are assumed here.
    """
    records = parse_jsonl(text)
    required = set(required_fields) | set(allowed_values)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("A diagnostic record must be a JSON object")
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Missing diagnostic fields: {sorted(missing)!r}")
        for field, permitted in allowed_values.items():
            if record[field] not in permitted:
                raise ValueError(f"Unknown diagnostic value for {field}: {record[field]!r}")
    return records


def read_zip(path):
    """Return all ZIP file members as name -> bytes without filesystem extraction.

    Directory entries are omitted; duplicate file names raise to avoid losing
    data. ZIP, checksum and I/O errors propagate. No exit status is involved.
    """
    result = {}
    with _zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if member.filename in result:
                raise ValueError(f"Duplicate ZIP member: {member.filename}")
            result[member.filename] = archive.read(member)
    return result


def read_tar(path):
    """Return tar members as name -> (kind, bytes-or-link-target).

    Kinds are file, directory, symlink and hardlink. Links are recorded, never
    followed or extracted. Duplicate names and unsupported special members raise;
    tar and I/O failures propagate. No process or status interpretation occurs.
    """
    result = {}
    with _tarfile.open(path, mode="r:*") as archive:
        for member in archive:
            if member.name in result:
                raise ValueError(f"Duplicate tar member: {member.name}")
            if member.isfile():
                with archive.extractfile(member) as stream:
                    value = ("file", stream.read())
            elif member.isdir():
                value = ("directory", None)
            elif member.issym():
                value = ("symlink", member.linkname)
            elif member.islnk():
                value = ("hardlink", member.linkname)
            else:
                raise ValueError(f"Unsupported tar member type: {member.name}")
            result[member.name] = value
    return result


def parse_metadata(data):
    """Return an email Message parsed from distribution metadata bytes.

    Repeated headers remain accessible via get_all and the payload is preserved.
    Parser defects raise under the strict policy; no product fields, expected
    values or process statuses are checked.
    """
    return _email_parser.BytesParser(policy=_email_policy.strict).parsebytes(data)


def parse_entry_points(text):
    """Return entry-point groups as group -> {case-preserved name: value}.

    Uses ConfigParser without interpolation. Malformed input or DEFAULT entries
    raise; no entry-point target is imported and no exit status is interpreted.
    """
    parser = _configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(text)
    if parser.defaults():
        raise ValueError("Entry-point metadata cannot contain DEFAULT entries")
    return {section: dict(parser.items(section)) for section in parser.sections()}


def _file_state(path):
    info = path.lstat()
    mode = _stat.S_IMODE(info.st_mode)
    if _stat.S_ISLNK(info.st_mode):
        return ("symlink", mode, _os.readlink(path))
    if _stat.S_ISREG(info.st_mode):
        return ("file", mode, path.read_bytes())
    if _stat.S_ISDIR(info.st_mode):
        return ("directory", mode, None)
    raise ValueError(f"Unsupported filesystem object: {path}")


def snapshot_files(paths):
    """Return supplied paths -> (kind, permission bits, contents/link target).

    An explicitly requested absent path maps to None, including when a parent
    is absent. Broken symlinks are recorded as links. Other observation errors
    propagate. Directories are recorded non-recursively. No process runs.
    """
    result = {}
    for supplied in paths:
        path = _Path(supplied)
        try:
            path.lstat()
        except FileNotFoundError:
            result[path] = None
        else:
            result[path] = _file_state(path)
    return result


def snapshot_tree(root):
    """Return relative paths -> file states for a complete existing directory tree.

    Includes '.' and empty directories; symlinks are not traversed. Missing
    roots, traversal races, permission errors and special objects raise. Contents
    and permission bits are captured, not timestamps. No exit status is involved.
    """
    root = _Path(root)
    if not _stat.S_ISDIR(root.lstat().st_mode):
        raise NotADirectoryError(root)
    result = {}

    def visit(path):
        state = _file_state(path)
        result[path.relative_to(root).as_posix()] = state
        if state[0] == "directory":
            for child in sorted(path.iterdir()):
                visit(child)

    visit(root)
    return result


def run_python(interpreter, source, args=(), *, cwd, env, stdin="", timeout=60.0):
    """Return CommandResult for supplied source executed by an explicit Python.

    Uses -B to avoid probe-created bytecode. Arguments follow -c source; stdin,
    status, errors and timeout semantics are exactly those of run_cli. Source
    must use plain public imports when it accesses the product.
    """
    return run_cli((interpreter,), ("-B", "-c", source, *args), cwd=cwd,
                   env=env, stdin=stdin, timeout=timeout)


_PROBE_SOURCE = '''import importlib.metadata as metadata
import json
import os
import sys

def application():
{application}

application_result = application()
distributions = []
for distribution in metadata.distributions():
    distributions.append({{
        "name": distribution.metadata["Name"],
        "version": distribution.version,
        "metadata": list(distribution.metadata.items()),
        "entry_points": [{{"group": ep.group, "name": ep.name, "value": ep.value}}
                         for ep in distribution.entry_points],
    }})
print(json.dumps({{
    "executable": sys.executable,
    "version": list(sys.version_info),
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "argv": sys.argv,
    "cwd": os.getcwd(),
    "distributions": distributions,
    "application": application_result,
}}, allow_nan=False))
'''


def probe_python(interpreter, *, cwd, env, application_source="return None",
                 args=(), timeout=60.0):
    """Return independent interpreter, argv, cwd, metadata and application JSON.

    application_source is a function body containing explicit imports and a
    JSON-serializable return value. It executes real code in the target Python;
    stdout must remain reserved for the probe JSON. -B suppresses new bytecode.
    Nonzero status raises CalledProcessError retaining both channels. Invalid or
    contaminated JSON, launch failures and bounded timeouts raise, never an empty
    installed set. This observes the interpreter, not product report semantics.
    """
    body = "\n".join("    " + line for line in application_source.splitlines())
    source = _PROBE_SOURCE.format(application=body)
    result = run_python(interpreter, source, args, cwd=cwd, env=env, timeout=timeout)
    if result.returncode != 0:
        raise _subprocess.CalledProcessError(
            result.returncode, result.args, output=result.stdout, stderr=result.stderr)
    return parse_json(result.stdout)


def snapshot_installed(interpreter, *, cwd, env, timeout=60.0):
    """Return the probe's list of installed distribution metadata records.

    Duplicate distributions and original names are retained; no ordering or
    normalization is imposed. Records include name, version, repeated metadata
    headers and entry points. Nonzero status and all observation errors raise
    with probe_python's semantics; this does not check expected installation.
    """
    return probe_python(interpreter, cwd=cwd, env=env,
                        timeout=timeout)["distributions"]
