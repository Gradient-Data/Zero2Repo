# feature: F00
"""Shared public-process machinery; no product expectations or entry paths.

Commands are argument sequences, never shell programs. The harness working
directory is the built product; callers supply entry points and any documented
 build commands. Feature adapters must use public C/Zig APIs and serialize real
 observations. Their guest errors belong in their JSON payload; adapter process
 failure is a driving failure. No product modules are imported here.

CLI scalar grammar and diagnostic labels are supplied by the owning contract.
This module deliberately does not infer them from explanatory output. Keep
failure_scope open through all deferred reads and resource cleanup. No helper
turns missing observations into None, empty data, or a successful outcome.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import json as _json
import math as _math
import os as _os
import pathlib as _pathlib
import shutil as _shutil
import signal as _signal
import subprocess as _subprocess
import tempfile as _tempfile
import time as _time

__all__ = [
    "HarnessError", "ProcessResult", "JsonResult", "BuildResult",
    "make_environment", "temporary_workspace", "discover_executable",
    "run_process", "run_cli", "run_json_adapter", "record_tool_versions",
    "build_outputs", "parse_json", "parse_scalar_lines", "read_label",
    "parse_unsigned_decimal", "failure_scope",
]


class HarnessError(AssertionError):
    """A driving/observation failure, never a product answer.

    result retains a ProcessResult when available; cause is also exception-chained
    when wrapping another error. stage and unobserved identify prerequisite
    failures and dependent observations that were not attempted.
    """

    def __init__(self, message, *, result=None, stage=None, unobserved=()):
        """Return an exception carrying raw evidence; no exit code is invented."""
        super().__init__(message)
        self.result = result
        self.stage = stage
        self.unobserved = tuple(unobserved)


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Captured command, absolute cwd, raw bytes, exit status and elapsed seconds.

    returncode is the OS process status (negative means signal on POSIX).
    run_process returns normally only for nonnegative statuses, including nonzero
    statuses. On timeout/crash a partial result is attached to HarnessError;
    returncode may be None if bounded cleanup could not reap the process.
    """

    argv: tuple
    cwd: _pathlib.Path
    returncode: object
    stdout: bytes
    stderr: bytes
    elapsed: float


@_dataclasses.dataclass(frozen=True)
class JsonResult:
    """Adapter process evidence and parsed JSON value, without behavior checks.

    process preserves status and raw channels; value may be any JSON value.
    Adapter nonzero status or malformed JSON raises instead of returning this.
    """

    process: ProcessResult
    value: object


@_dataclasses.dataclass(frozen=True)
class BuildResult:
    """Fresh output paths, build evidence, declared config and raw tool versions.

    configuration is caller-supplied metadata, not inferred product capability.
    Build/tool failures raise with process evidence; no previous output is used.
    """

    outputs: tuple
    process: ProcessResult
    configuration: dict
    tool_versions: dict


def _seconds(value):
    value = float(value)
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and positive")
    return value


def _argv(command):
    if isinstance(command, (str, bytes, _os.PathLike)):
        raise TypeError("Command must be an argument sequence, not a shell string")
    result = tuple(_os.fspath(part) for part in command)
    if not result:
        raise ValueError("Command must contain an executable")
    return result


def make_environment(updates=None, *, remove=(), base=None):
    """Return a fresh child environment; never mutate the current process.

    base=None copies os.environ; an explicit mapping replaces that base exactly.
    remove deletes named entries, including already absent ones. updates must
    contain string keys/values; invalid inputs raise. No process status applies.
    """
    result = dict(_os.environ if base is None else base)
    for key in remove:
        result.pop(key, None)
    if updates is not None:
        result.update(updates)
    if any(not isinstance(k, str) or not isinstance(v, str)
           for k, v in result.items()):
        raise TypeError("Environment keys and values must be strings")
    return result


@_contextlib.contextmanager
def temporary_workspace(*, parent=None, prefix="suite-"):
    """Yield a unique pathlib.Path and remove only that directory on exit.

    Does not change cwd or environment. Creation, body and cleanup errors
    propagate; no exit status or fabricated missing-file value is returned.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as directory:
        yield _pathlib.Path(directory)


def discover_executable(entry, *, cwd=None, env=None):
    """Return an absolute executable path for an explicit path or PATH name.

    Relative paths use cwd (current directory when omitted). Bare names use the
    supplied environment's PATH, or the current PATH when env is omitted; an
    absent PATH searches nothing. No repository-layout guesses or builds occur.
    Missing/nonexecutable entries raise HarnessError; there is no exit status.
    """
    root = _pathlib.Path.cwd() if cwd is None else _pathlib.Path(cwd).resolve()
    name = _os.fsdecode(_os.fspath(entry))
    if not name:
        raise ValueError("Executable entry must not be empty")
    if _os.path.isabs(name) or _os.path.dirname(name):
        path = _pathlib.Path(name)
        if not path.is_absolute():
            path = root / path
    else:
        environment = _os.environ if env is None else env
        search = environment.get("PATH", "")
        directories = [] if not search else [
            str((_pathlib.Path(p) if _pathlib.Path(p).is_absolute()
                 else root / p)) for p in search.split(_os.pathsep)
        ]
        found = _shutil.which(name, path=_os.pathsep.join(directories)) if directories else None
        if found is None:
            raise HarnessError(f"Executable not found on the supplied PATH: {name!r}")
        path = _pathlib.Path(found)
    if not path.is_file() or not _os.access(path, _os.X_OK):
        raise HarnessError(f"Executable is missing or not executable: {path}")
    return path.absolute()


def run_process(command, *, input_bytes=b"", cwd=None, env=None,
                timeout=30.0, cleanup_timeout=5.0):
    """Return ProcessResult with raw stdout/stderr and ordinary exit status.

    stdin receives exactly input_bytes followed by EOF. env=None inherits the
    host environment; a mapping replaces it. No shell is used. Nonzero ordinary
    exits are returned for feature assertions. Launch errors, signals and outer
    timeouts raise HarnessError, with original cause and captured bytes when
    available. POSIX children run in a new session; timeout/abort kills that
    owned process group and bounds draining/reaping by cleanup_timeout. On other
    platforms only the direct child can be killed. No timeout is guest failure.
    """
    timeout = _seconds(timeout)
    cleanup_timeout = _seconds(cleanup_timeout)
    argv = _argv(command)
    if not isinstance(input_bytes, bytes):
        raise TypeError("input_bytes must be bytes")
    root = _pathlib.Path.cwd() if cwd is None else _pathlib.Path(cwd).resolve()
    started = _time.monotonic()
    try:
        process = _subprocess.Popen(
            argv, cwd=root, env=env, stdin=_subprocess.PIPE,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            start_new_session=(_os.name == "posix"),
        )
    except (OSError, ValueError) as exc:
        raise HarnessError(f"Could not launch {argv!r}: {exc}") from exc
    try:
        stdout, stderr = process.communicate(input_bytes, timeout=timeout)
    except BaseException as original:
        stdout = getattr(original, "output", None) or b""
        stderr = getattr(original, "stderr", None) or b""
        cleanup_error = None
        try:
            try:
                if _os.name == "posix":
                    _os.killpg(process.pid, _signal.SIGKILL)
                elif process.poll() is None:
                    process.kill()
            except ProcessLookupError:
                # ESRCH explicitly means the owned process/group is gone.
                pass
            stdout, stderr = process.communicate(timeout=cleanup_timeout)
        except Exception as exc:
            cleanup_error = exc
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        result = ProcessResult(argv, root, process.poll(), stdout, stderr,
                               _time.monotonic() - started)
        if isinstance(original, (KeyboardInterrupt, SystemExit)):
            if cleanup_error is not None:
                raise HarnessError(f"Cleanup failed: {cleanup_error}", result=result) from original
            raise
        detail = f"; cleanup failed: {cleanup_error!r}" if cleanup_error is not None else ""
        raise HarnessError(f"Process driving failed for {argv!r}: {original}{detail}",
                           result=result) from original
    result = ProcessResult(argv, root, process.returncode, stdout, stderr,
                           _time.monotonic() - started)
    if result.returncode < 0:
        raise HarnessError(f"Process terminated by signal {-result.returncode}: {argv!r}",
                           result=result)
    return result


def run_cli(entry, arguments=(), **process_options):
    """Return raw ProcessResult for an explicit CLI entry and argument sequence.

    No subcommand, flag or result interpretation is added. Ordinary nonzero
    exits are returned; driving failures raise as documented by run_process.
    """
    if isinstance(arguments, (str, bytes)):
        raise TypeError("CLI arguments must be a sequence of arguments")
    return run_process((_os.fspath(entry), *arguments), **process_options)


def _require_tool_success(result):
    if result.returncode != 0:
        raise HarnessError(f"Tool/adapter exited with status {result.returncode}: {result.argv!r}\n"
                           f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}",
                           result=result)
    return result


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def parse_json(data):
    """Return the value of one entire JSON document, including a genuine null.

    Uses the JSON parser, never extracts a substring. Duplicate keys and non-JSON
    constants are observation errors. Malformed/undecodable input raises
    HarnessError chained to the parser error; no process exit status is assumed.
    """
    try:
        return _json.loads(data, object_pairs_hook=_json_pairs,
                           parse_constant=_json_constant)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise HarnessError(f"Could not read JSON document: {exc}") from exc


def run_json_adapter(command, **process_options):
    """Return JsonResult from a caller-provided public C/Zig adapter command.

    The adapter contract is one complete JSON document on stdout, diagnostics on
    stderr, and zero exit status for a completed observation (including reported
    product rejection). Nonzero adapter exit, crash, timeout or malformed JSON
    raises with raw process evidence. No payload schema or product rule is imposed.
    """
    result = _require_tool_success(run_process(command, **process_options))
    try:
        value = parse_json(result.stdout)
    except HarnessError as exc:
        raise HarnessError(str(exc), result=result) from exc
    return JsonResult(result, value)


def _output_lines(text):
    # A final bare CR is content; only a CR immediately before LF is framing.
    parts = text.split("\n")
    lines = [part[:-1] if part.endswith("\r") else part
             for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def parse_scalar_lines(data, parse_line, *, encoding="utf-8"):
    """Return ordered values parsed from every LF-delimited CLI scalar line.

    parse_line must implement the published whole-line scalar grammar and raise
    on invalid/trailing text. Only one final LF and each CR in CRLF are removed;
    blank lines, spaces and guest text are never filtered. Empty output returns
    an empty tuple, without claiming success or checking expected result count.
    Decode/parser errors raise with their original cause; status stays separate.
    """
    try:
        text = data.decode(encoding) if isinstance(data, bytes) else data
        return tuple(parse_line(line) for line in _output_lines(text))
    except Exception as exc:
        raise HarnessError(f"Could not parse scalar output: {exc}") from exc


def read_label(data, label, *, separator=": ", encoding="utf-8"):
    """Return the verbatim value of exactly one explicitly named line field.

    Reads only lines starting with label + separator, without guessing from
    prose or position. Missing/duplicate fields raise HarnessError; no absence
    or success is inferred. Call only where the contract declares this field.
    LF/CRLF terminators are removed; a final bare CR is preserved as content.
    Caller chooses the documented output channel; process status is untouched.
    """
    if not label or not separator or "\n" in label or "\r" in label:
        raise ValueError("A nonempty single-line label and separator are required")
    try:
        text = data.decode(encoding) if isinstance(data, bytes) else data
        prefix = label + separator
        values = []
        for line in _output_lines(text):
            if line.startswith(prefix):
                values.append(line[len(prefix):])
    except (UnicodeError, TypeError, AttributeError) as exc:
        raise HarnessError(f"Could not read labeled output: {exc}") from exc
    if len(values) != 1:
        raise HarnessError(f"Expected one field {label!r}; observed {len(values)}")
    return values[0]


def parse_unsigned_decimal(text):
    """Return an integer from an entire nonempty ASCII decimal field.

    No signs, spaces or trailing text are consumed. Invalid syntax raises
    HarnessError; this parser neither checks a product limit nor an exit status.
    """
    if not isinstance(text, str) or not text or any(c < "0" or c > "9" for c in text):
        raise HarnessError(f"Invalid unsigned decimal field: {text!r}")
    try:
        return int(text, 10)
    except ValueError as exc:
        raise HarnessError(f"Could not decode unsigned decimal field: {exc}") from exc


def record_tool_versions(commands, *, cwd=None, env=None, timeout=30.0):
    """Return name -> ProcessResult for caller-specified version commands.

    Both raw channels are retained, never guessed or normalized into versions.
    Every command must finish with zero status; missing tools, nonzero status,
    crash or timeout raise. Each command has its own finite timeout.
    """
    return {name: _require_tool_success(run_process(
        command, cwd=cwd, env=env, timeout=timeout
    )) for name, command in commands.items()}


def build_outputs(command, outputs, *, configuration, version_commands,
                  cwd=None, env=None, timeout=300.0, version_timeout=30.0):
    """Return BuildResult after a successful explicit public build command.

    All declared outputs must be absent before invocation and regular files
    afterward. Existing outputs (including broken symlinks) raise without being
    deleted; use a fresh temporary directory and pass its paths in the command.
    Records caller configuration, tool-version observations and raw build output.
    Nonzero tool/build status or missing outputs raise, never reuse old artifacts.
    Paths are relative to cwd; configuration is recorded, not translated to flags.
    """
    root = _pathlib.Path.cwd() if cwd is None else _pathlib.Path(cwd).resolve()
    paths = tuple(p if p.is_absolute() else root / p
                  for p in map(_pathlib.Path, outputs))
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("Declare at least one output and no duplicate paths")
    for path in paths:
        if _os.path.lexists(path):
            raise HarnessError(f"Build output already exists: {path}")
    config = dict(configuration)
    versions = record_tool_versions(version_commands, cwd=root, env=env,
                                    timeout=version_timeout)
    result = _require_tool_success(run_process(command, cwd=root, env=env,
                                               timeout=timeout))
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise HarnessError(f"Build did not create a regular output file: {path}",
                               result=result)
    return BuildResult(paths, result, config, versions)


@_contextlib.contextmanager
def failure_scope(stage, *, unobserved=()):
    """Yield None; re-raise failures with prerequisite/dependency provenance.

    Enclose invocation, complete deferred result consumption and cleanup in the
    same scope. Exceptions become HarnessError with the original exception as
    cause, stage name, dependent observation names, and any raw process result.
    This does not catch product errors encoded as ordinary returned data, assert
    behavior, execute deferred work, or impose a deadline on arbitrary Python.
    Process/network operations inside must use their own bounded primitives.
    """
    dependencies = tuple(unobserved)
    try:
        yield
    except Exception as exc:
        raise HarnessError(
            f"Stage {stage!r} failed; dependent observations not completed: "
            f"{dependencies!r}: {exc}",
            result=getattr(exc, "result", None), stage=stage,
            unobserved=dependencies,
        ) from exc

# A plan owns one immutable input epoch and fresh output tree. No guest result
# is cached. Source watches make mutations explicit without rescanning on hits.
import atexit as _atexit
import ctypes as _ctypes
import hashlib as _hashlib
import re as _re
import sys as _sys

_TOKEN = _re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*|\s+|.', _re.S)


def _digest(path):
    with open(path, 'rb') as stream:
        return _hashlib.file_digest(stream, 'sha256').hexdigest()


def _c_functions(source):
    """Find defined C functions, excluding declarations and preprocessor bodies.

    Consumers are ordinary C translation units. This lexical pass only assigns
    private link names; it never interprets guest data or product output.
    """
    source = _re.sub(r'^\s*#(?:[^\n\\]|\\.)*(?:\\\n[^\n]*)*', '', source, flags=_re.M)
    tokens = [t for t in _TOKEN.findall(source)
              if not t.isspace() and not t.startswith(('//', '/*'))]
    depth = 0
    boundary = 0
    names = set()
    for i, token in enumerate(tokens):
        if token == '{':
            if depth == 0 and i and tokens[i - 1] == ')' and 'static' not in tokens[boundary:i]:
                parens, j = 1, i - 2
                while j >= 0 and parens:
                    parens += (tokens[j] == ')') - (tokens[j] == '(')
                    j -= 1
                if j >= 0:
                    names.add(tokens[j])
            depth += 1
        elif token == '}':
            depth -= 1
            if depth == 0:
                boundary = i + 1
        elif token == ';' and depth == 0:
            boundary = i + 1
    if depth != 0:
        raise HarnessError('Unbalanced consumer C translation unit')
    return names


def _rename(source, names):
    return ''.join(names.get(token, token) for token in _TOKEN.findall(source))


def _walk_failure(error):
    raise error


class _InputEpoch:
    """Inventory once; Linux directory watches invalidate the entire epoch."""
    def __init__(self, roots):
        libc = _ctypes.CDLL(None, use_errno=True)
        self.libc = libc
        self.fd = libc.inotify_init1(_os.O_NONBLOCK | _os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(_ctypes.get_errno(), 'Cannot watch build inputs')
        self.invalid = False
        self.identity = _hashlib.sha256()
        seen = set()
        for root in roots:
            root = _pathlib.Path(root).resolve()
            if not root.is_dir():
                raise HarnessError(f'Build input directory is missing: {root}')
            for directory, dirs, files in _os.walk(root, followlinks=True, onerror=_walk_failure):
                dirs[:] = sorted(d for d in dirs if d not in ('.git', '.zig-cache', 'zig-out', '__pycache__', '.pytest_cache'))
                resolved = str(_pathlib.Path(directory).resolve())
                if resolved in seen:
                    dirs[:] = []
                    continue
                seen.add(resolved)
                for name in dirs + files:
                    path = _pathlib.Path(directory) / name
                    if path.is_symlink():
                        self.identity.update(str(path).encode())
                        self.identity.update(_os.fsencode(_os.readlink(path)))
                # Writes, replacement, removal, attribute changes and queue overflow
                # invalidate. Access events caused by compilation are excluded.
                if libc.inotify_add_watch(self.fd, _os.fsencode(directory), 0x00000fce) < 0:
                    raise OSError(_ctypes.get_errno(), f'Cannot watch {directory}')
                for name in sorted(files):
                    path = _pathlib.Path(directory) / name
                    if path.is_file():
                        if path.is_symlink():
                            self.watch_files([path.resolve()])
                        self.identity.update(str(path).encode())
                        self.identity.update(bytes.fromhex(_digest(path)))
        self.check()

    def watch_files(self, paths):
        for path in paths:
            if self.libc.inotify_add_watch(self.fd, _os.fsencode(path), 0x00000fce) < 0:
                raise OSError(_ctypes.get_errno(), f'Cannot watch generated input {path}')

    def check(self):
        if self.invalid:
            raise HarnessError('Build input epoch is invalid; start a new run')
        try:
            events = _os.read(self.fd, 1 << 20)
        except BlockingIOError:
            return
        if events:
            self.invalid = True
            raise HarnessError('Build inputs changed during the run-owned input epoch; start a new run')

    def close(self):
        self.check()
        _os.close(self.fd)


class BuildPlan:
    """Suite-wide compilation and artifact bindings, scoped to one driver session.

    Target is Zig's native target (recorded by `zig env`); every build option is
    part of its group. Inputs must remain unchanged until close. Changes require
    a new plan, never reuse under a changed identity. Output stat seals are checked
    at every binding/execution; any change is an error, not a rebuild fallback.
    """
    def __init__(self, checkout, directory, consumers, cli_sources):
        started = _time.monotonic()
        self.root = _pathlib.Path(checkout).resolve()
        self.directory = _pathlib.Path(directory)
        self.directory.mkdir()
        self.sources = dict(consumers)
        self.cli_sources = cli_sources
        self.environment = make_environment()
        self.environment['ZIG_GLOBAL_CACHE_DIR'] = str(self.directory / 'global-cache')
        self.environment['ZIG_LOCAL_CACHE_DIR'] = str(self.directory / 'local-cache')
        self.environment.pop('PYTEST_CURRENT_TEST', None)
        self.versions = record_tool_versions({'zig': ['zig', 'version'], 'zig-env': ['zig', 'env'],
                                               'wasm-tools': ['wasm-tools', '--version']}, env=self.environment)
        lib_fields = _re.findall(r'^    \.lib_dir = (".*"),$', self.versions['zig-env'].stdout.decode(), _re.M)
        if len(lib_fields) != 1:
            raise HarnessError('Cannot read Zig library directory from zig env')
        zig_lib = _json.loads(lib_fields[0])
        zig = discover_executable('zig', env=self.environment)
        self.epoch = _InputEpoch((self.root, _pathlib.Path(__file__).parent, zig.resolve().parent, zig_lib))
        identity = dict(checkout=str(self.root), inputs=self.epoch.identity.hexdigest(),
                        sources=self.sources, cli=cli_sources, environment=self.environment,
                        compiler=str(zig), compiler_sha256=_digest(zig),
                        tools={k: v.stdout.decode() for k, v in self.versions.items()})
        self.identity = _hashlib.sha256(_json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.manifest = dict(checkout=str(self.root), input_sha256=self.epoch.identity.hexdigest(),
                             consumer_sha256=_hashlib.sha256(_json.dumps(self.sources, sort_keys=True).encode()).hexdigest(),
                             environment_sha256=_hashlib.sha256(_json.dumps(self.environment, sort_keys=True).encode()).hexdigest(),
                             compiler=str(zig), compiler_sha256=_digest(zig),
                             tool_versions={k: v.stdout.decode() for k,v in self.versions.items()})
        self.project_inputs = {}
        self.failures = {}
        self.groups = {}
        self.artifacts = {}
        self.trace = []
        self.executions = {}
        self.closed = False
        self._event('preparation', started, identity=self.identity, cache='fresh run-owned global and local caches')
        _atexit.register(self.report)

    def _event(self, stage, started, **fields):
        self.trace.append(dict(stage=stage, seconds=_time.monotonic()-started, **fields))

    def _check(self):
        self.epoch.check()
        # The child environment was captured once; changing the parent's build
        # environment invalidates this plan instead of silently reusing binaries.
        current = make_environment()
        expected = {k: v for k, v in self.environment.items()
                    if k not in ('ZIG_GLOBAL_CACHE_DIR', 'ZIG_LOCAL_CACHE_DIR')}
        current = {k: v for k, v in current.items()
                   if k not in ('ZIG_GLOBAL_CACHE_DIR', 'ZIG_LOCAL_CACHE_DIR')}
        # Pytest updates this observation label for every test; it is not a build input.
        current.pop('PYTEST_CURRENT_TEST', None)
        expected.pop('PYTEST_CURRENT_TEST', None)
        if current != expected:
            raise HarnessError('Build environment changed during the input epoch')

    def _seal(self, path):
        if not path.is_file() or path.is_symlink():
            raise HarnessError(f'Build artifact is not a regular file: {path}')
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_mode

    def _bind(self, path):
        self.artifacts[path] = (self._seal(path), _digest(path))
        _BOUND_ARTIFACTS[str(path)] = self
        return path

    def verify(self, path):
        self._check()
        if self._seal(path) != self.artifacts[path][0]:
            raise HarnessError(f'Registered build artifact changed: {path}')

    def _project(self, name, build, files):
        project = self.directory / name
        project.mkdir()
        (project / 'build.zig').write_text(build)
        for name, source in files.items():
            (project / name).write_text(source)
        (project / 'build.zig.zon').write_text('''.{
.name = .navor_zig_dep_example, .version = "0.0.0",
.fingerprint = 0x9f4ddfc6ccf608c2, .minimum_zig_version = "0.16.0",
.dependencies = .{ .navor = .{ .path = %s } },
.paths = .{ "." },
}''' % _json.dumps(_os.path.relpath(self.root, project)))
        inputs = [project/'build.zig', project/'build.zig.zon', *[project/name for name in files]]
        self.epoch.watch_files(inputs)
        self.project_inputs[project.name] = {path.name: _digest(path) for path in inputs}
        return project

    def _build(self, project, options, outputs):
        self._check()
        started = _time.monotonic()
        try:
            result = build_outputs(['zig', 'build', '-j2', *[f'-D{k}={v}' for k,v in options.items()]],
                                   outputs, configuration=options, version_commands={},
                                   cwd=project, env=self.environment, timeout=300)
        except HarnessError as error:
            self.failures[project.name] = error
            self._event('compilation', started, project=str(project), options=options,
                        failed=True, diagnostic=str(error))
            raise
        self._event('compilation', started, project=str(project), options=options,
                    command=result.process.argv, returncode=result.process.returncode,
                    input_sha256=self.project_inputs[project.name])
        return result

    def consumer(self, name, *, level='v3_0', source=None):
        started = _time.monotonic()
        self._check()
        if source is not None and self.sources[name][0] != source:
            raise HarnessError(f'Consumer source differs from its registered plan entry: {name}')
        key = ('consumers', level)
        if key not in self.groups:
            # Publish failure before attempting preparation: no partial output may
            # become a successful binding after a failed build.
            self.groups[key] = None
            selected = {n: s for n, s in self.sources.items() if level in s[2]}
            if name not in selected:
                raise HarnessError(f'Consumer {name} does not support {level}')
            files, branches, c_sources = {}, [], []
            for index, (consumer, (zig, c, levels)) in enumerate(selected.items()):
                exports = set(_re.findall(r'\bexport\s+fn\s+(\w+)', zig))
                names = {symbol: f'consumer_{index}_{symbol}'
                         for symbol in _c_functions(c) | exports}
                zig = _rename(zig, names)
                entry = names['main']
                zig = zig.replace(f'pub export fn {entry}', f'pub fn {entry}')
                files[f'consumer{index}.zig'] = zig
                files[f'consumer{index}.c'] = _rename(c, names)
                branches.append(f'    if (std.mem.eql(u8, name, "{consumer}")) return @import("consumer{index}.zig").{entry}(argc, argv);')
                c_sources.append(f'    exe.root_module.addCSourceFile(.{{ .file = b.path("consumer{index}.c"), .flags = &.{{"-std=c11", "-Wall", "-Werror"}} }});')
            files['probe.zig'] = '''const std = @import("std");
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int {
    const name = std.fs.path.basename(std.mem.span(argv[0]));
'''+'\n'.join(branches)+'''\n    std.debug.print("Unknown consumer entry: {s}\\n", .{name});
    return 64;
}
'''
            from F01_helpers import F01_BUILD
            build = F01_BUILD.replace('f01-probe', 'suite-consumers')
            old = '    exe.root_module.addCSourceFile(.{ .file = b.path("probe.c"), .flags = &.{"-std=c11", "-Wall", "-Werror"} });'
            if build.count(old) != 1:
                raise HarnessError('Consumer build template changed; update the build plan')
            build = build.replace(old, '\n'.join(c_sources))
            project = self._project('consumers-'+level, build, files)
            self._event('preparation', started, group=key, consumers=list(selected))
            output = project / 'zig-out/bin/suite-consumers'
            self._build(project, dict(optimize='ReleaseSafe', wasm=level), [output])
            paths = {}
            for consumer in selected:
                path = output.with_name(consumer)
                _os.link(output, path)
                paths[consumer] = path
            # Hardlinks change ctime, so seal only after all links have been made.
            self.groups[key] = {n: self._bind(p) for n,p in paths.items()}
        if self.groups[key] is None:
            raise HarnessError(f'Build prerequisite failed for {key}; dependent observation unobserved') from self.failures.get('consumers-'+level)
        started = _time.monotonic()
        output = self.groups[key][name]
        self.verify(output)
        self._event('reuse', started, consumer=name, group=key, artifact=str(output))
        return output

    def cli(self, *, consumer, wasm, wasi, engine, optimize):
        started = _time.monotonic()
        self._check()
        config = dict(wasm=wasm, wasi=wasi, engine=engine, optimize=optimize)
        key = ('cli', *config.values())
        if key not in self.groups:
            self.groups[key] = None
            build, zig, c = self.cli_sources
            project = self._project('-'.join(key), build, {'probe.zig': zig, 'probe.c': c})
            self._event('preparation', started, group=key)
            outputs = [project/'zig-out/bin/navor', project/'zig-out/bin/f11-version']
            self._build(project, config, outputs)
            self.groups[key] = tuple(self._bind(path) for path in outputs)
        if self.groups[key] is None:
            raise HarnessError(f'Build prerequisite failed for {key}; dependent observation unobserved') from self.failures.get('-'.join(key))
        started = _time.monotonic()
        for path in self.groups[key]:
            self.verify(path)
        self._event('reuse', started, consumer=consumer, group=key, artifacts=list(map(str,self.groups[key])))
        return self.groups[key]

    def close(self):
        if self.closed:
            return
        self.closed = True
        for path in self.artifacts:
            self.verify(path)
        self.epoch.close()

    def report(self):
        print('BUILD_TRACE '+_json.dumps(dict(identity=self.identity, manifest=self.manifest, events=self.trace,
                                             executions=self.executions)), file=_sys.stderr)


_BOUND_ARTIFACTS = {}


@_contextlib.contextmanager
def execution_scope(entry):
    """Verify a registered executable and time a fresh observation, including errors."""
    name = _os.fspath(entry)
    plan = _BOUND_ARTIFACTS.get(name)
    if plan is not None:
        plan.verify(_pathlib.Path(name))
    started = _time.monotonic()
    try:
        yield
    finally:
        if plan is not None:
            item = plan.executions.setdefault(name, dict(count=0, seconds=0.0))
            item['count'] += 1
            item['seconds'] += _time.monotonic() - started


_run_process_untraced = run_process


def run_process(command, **options):
    argv = _argv(command)
    with execution_scope(argv[0]):
        return _run_process_untraced(argv, **options)


def trace_execution(function):
    """Keep direct PTY/pipe observations within the same verification boundary."""
    import functools
    @functools.wraps(function)
    def traced(entry, *args, **kwargs):
        with execution_scope(entry):
            return function(entry, *args, **kwargs)
    return traced


def trace_consumer_execution(function):
    """Instrument interactive driver methods that directly manage their child."""
    import functools
    @functools.wraps(function)
    def traced(driver, *args, **kwargs):
        with execution_scope(driver.program()):
            return function(driver, *args, **kwargs)
    return traced
