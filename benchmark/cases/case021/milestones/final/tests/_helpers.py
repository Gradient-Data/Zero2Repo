# feature: F00
"""Shared drivers only. Feature tests own all product expectations.

Children keep the product working directory. Support files use absolute paths.
Entrypoints and application source come from callers, with plain public imports.
No diagnostic, annotation or debugger output meaning is guessed here.
"""
import contextlib as _contextlib
import dataclasses as _dataclasses
import html.parser as _html
import io as _io
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import shutil as _shutil
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import time as _time
import traceback as _traceback
import uuid as _uuid
import xml.etree.ElementTree as _xml

__all__ = ["CommandResult", "CommandTimeout", "Observation", "Project", "HTMLNode",
           "DependencyRule", "temporary_project", "unique_module_name", "environment",
           "tool_path", "run_command", "run_python", "run_module", "build_extensions",
           "build_native", "observe", "parse_json", "parse_html", "parse_xml",
           "parse_make_dependencies"]


@_dataclasses.dataclass(frozen=True)
class CommandResult:
    """Raw argv, cwd, exit status, byte streams and elapsed wall seconds.

    Nonzero status is data; negative status denotes a POSIX signal. Launch and
    harness failures raise instead of producing this result.
    """
    argv: tuple
    cwd: _Path
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed: float

    def check_returncode(self):
        """Return self on zero; otherwise raise CalledProcessError with both streams.

        Intended for prerequisites; product rejection tests inspect status directly.
        """
        if self.returncode:
            raise _subprocess.CalledProcessError(self.returncode, self.argv,
                                                output=self.stdout, stderr=self.stderr)
        return self

    def text(self, channel="stdout", encoding="utf-8"):
        """Return a strictly decoded named stream; bad channel/encoding/data raise.

        Does not inspect or reinterpret exit status.
        """
        if channel not in ("stdout", "stderr"):
            raise ValueError("channel must be stdout or stderr")
        return getattr(self, channel).decode(encoding)


class CommandTimeout(AssertionError):
    """Harness timeout failure, retaining raw post-termination result and time limit.

    Never returned as a product rejection. Partial stdout/stderr remain available.
    """
    def __init__(self, result, timeout):
        """Store result/time limit and initialize the failure; return no value."""
        self.result, self.timeout = result, timeout
        super().__init__(f"Command exceeded {timeout}s: {result.argv!r}\n"
                         f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}")


def environment(overrides=None, *, base=None, import_paths=None):
    """Return a copied environment with edits; None-valued edits remove keys.

    base=None inherits the current environment; base={} inherits nothing.
    import_paths replaces PYTHONPATH with absolute paths (empty removes it).
    Invalid values raise; no process/status is produced.
    """
    result = dict(_os.environ if base is None else base)
    for key, value in (overrides or {}).items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _os.fspath(value) if isinstance(value, _os.PathLike) else str(value)
    if import_paths is not None:
        paths = [str(_Path(path).resolve()) for path in import_paths]
        if paths:
            result["PYTHONPATH"] = _os.pathsep.join(paths)
        else:
            result.pop("PYTHONPATH", None)
    return result


def tool_path(executable, *, env=None):
    """Return an absolute executable path; missing/nonexecutable tools raise.

    Uses the supplied environment's PATH without selecting an alternative tool.
    Package-manager callers must pass this absolute path to run_command.
    """
    found = _shutil.which(_os.fspath(executable),
                         path=(_os.environ if env is None else env).get("PATH", ""))
    if found is None:
        raise FileNotFoundError(f"Executable not found: {executable}")
    return _Path(found).absolute()


def _kill(process):
    if _os.name == "posix":
        try:
            _os.killpg(process.pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass  # The group already exited; this race is not a product outcome.
    elif process.poll() is None:
        process.kill()


def run_command(argv, *, product_dir=None, env=None, input=None, timeout=120):
    """Run argv without a shell; return CommandResult including nonzero exits.

    cwd is the product directory, defaulting to current cwd, never a scratch
    project. env is exact or None to inherit. input accepts bytes or UTF-8 text.
    Launch/I/O errors propagate. Timeout kills this command's process group and
    raises CommandTimeout; termination/pipe cleanup waits are also bounded.
    """
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if isinstance(argv, (str, bytes)):
        raise TypeError("argv must be an argument sequence")
    command = tuple(_os.fspath(arg) for arg in argv)
    if not command:
        raise ValueError("argv must not be empty")
    payload = input.encode("utf-8") if isinstance(input, str) else input
    if payload is not None and not isinstance(payload, bytes):
        raise TypeError("input must be bytes, text or None")
    cwd = _Path.cwd().resolve() if product_dir is None else _Path(product_dir).resolve(strict=True)
    start = _time.monotonic()
    process = _subprocess.Popen(command, cwd=cwd, env=env, stdin=_subprocess.PIPE,
                                stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
                                start_new_session=(_os.name == "posix"))
    try:
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except _subprocess.TimeoutExpired as cause:
            _kill(process)
            stdout, stderr = process.communicate(timeout=5)
            result = CommandResult(command, cwd, process.returncode, stdout, stderr,
                                   _time.monotonic() - start)
            raise CommandTimeout(result, timeout) from cause
        return CommandResult(command, cwd, process.returncode, stdout, stderr,
                             _time.monotonic() - start)
    finally:
        if process.poll() is None:
            _kill(process)
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def run_python(source, *, python=None, args=(), product_dir=None, env=None,
               input=None, timeout=120):
    """Run caller Python source in a fresh interpreter and return CommandResult.

    python selects the interpreter, defaulting to this interpreter. Product imports
    must be plain public imports in source. No path is injected. Exit status and
    errors follow run_command; uncaught application failures remain in stderr.
    """
    return run_command([_sys.executable if python is None else python, "-c", source, *args],
                       product_dir=product_dir, env=env, input=input, timeout=timeout)


def run_module(module, args=(), *, python=None, product_dir=None, env=None,
               input=None, timeout=120):
    """Run a caller-selected public CLI via python -m; return CommandResult.

    No module/options are inferred. Status, errors and bounds follow run_command.
    """
    return run_command([_sys.executable if python is None else python, "-m", module, *args],
                       product_dir=product_dir, env=env, input=input, timeout=timeout)


@_dataclasses.dataclass(frozen=True)
class Project:
    """Temporary files root, never a child cwd; methods return paths/environments.

    Filesystem errors propagate. No product result or exit status is inferred.
    """
    root: _Path

    def path(self, relative):
        """Return a resolved path within this root; path escapes raise ValueError."""
        result = (self.root / relative).resolve()
        result.relative_to(self.root.resolve())
        return result

    def write(self, relative, content):
        """Write UTF-8 text or bytes and return the path; I/O/type errors propagate."""
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def environment(self, *, product_dir=None, import_paths=(), overrides=None, base=None):
        """Return an environment with project-owned home/cache/temp and controlled imports.

        Product root precedes explicit import_paths and this project; inherited
        PYTHONPATH is replaced, user site disabled. No installed tools are hidden:
        compiler-free target checks require the caller's actual target environment.
        Creation/configuration errors raise; no process/status is produced.
        """
        dirs = {key: self.path(".environment/" + key)
                for key in ("home", "cache", "config", "tmp")}
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        edits = {"HOME": dirs["home"], "USERPROFILE": dirs["home"],
                 "XDG_CACHE_HOME": dirs["cache"], "XDG_CONFIG_HOME": dirs["config"],
                 "TMPDIR": dirs["tmp"], "TEMP": dirs["tmp"], "TMP": dirs["tmp"],
                 "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        edits.update(overrides or {})
        root = _Path.cwd() if product_dir is None else _Path(product_dir)
        return environment(edits, base=base, import_paths=[root, *import_paths, self.root])


@_contextlib.contextmanager
def temporary_project(*, parent=None, prefix="suite-"):
    """Yield a new Project under parent or system temp, and remove it on exit.

    Creation/cleanup failures propagate. No cwd/global environment changes occur;
    no product status is represented. Parent must be writable if supplied.
    """
    with _tempfile.TemporaryDirectory(prefix=prefix, dir=parent) as path:
        yield Project(_Path(path).resolve())


def unique_module_name(prefix="suite"):
    """Return a fresh identifier for authored modules; invalid prefixes raise.

    Does not reserve/import anything or imply a product exit status.
    """
    if not prefix.isidentifier():
        raise ValueError("prefix must be a Python identifier")
    return prefix + "_" + _uuid.uuid4().hex


def build_extensions(project, extensions, *, python=None, product_dir=None,
                     env=None, timeout=180, setup_options=None, args=()):
    """Build native sources through public setuptools; return unchecked CommandResult.

    extensions contains Extension keyword dictionaries. Documented path fields are
    resolved against project.root. Sources must already be C/C++; this never calls
    translation. All other native settings pass through. Artifacts go to the
    project root, with temporary objects below it. Load via run_python using plain
    imports. setup_options supplies setup keywords except ext_modules/script_args.
    Build failures remain nonzero results; helper/I/O failures raise. Target
    interpreter/toolchain/environment are explicit; no installation is attempted.
    """
    specs = []
    for original in extensions:
        spec = dict(original)
        for key in ("sources", "include_dirs", "library_dirs", "runtime_library_dirs",
                    "extra_objects", "depends"):
            if key in spec:
                spec[key] = [str((project.root / path).resolve()) for path in spec[key]]
        specs.append(spec)
    options = dict(setup_options or {})
    if "ext_modules" in options or "script_args" in options:
        raise ValueError("ext_modules and script_args are managed by this helper")
    script = project.write(unique_module_name("build") + ".py",
        "from setuptools import Extension, setup\n"
        f"setup(ext_modules=[Extension(**s) for s in {specs!r}], **{options!r})\n")
    argv = [_sys.executable if python is None else python, str(script), "build_ext",
            "--build-lib", str(project.root), "--build-temp",
            str(project.path(".native-build")), *args]
    if env is None:
        env = project.environment(product_dir=product_dir)
    return run_command(argv, product_dir=product_dir, env=env, timeout=timeout)


def build_native(compiler, sources, output, *, before=(), after=(), product_dir=None,
                 env=None, timeout=180):
    """Run a supplied compiler driver and return unchecked CommandResult.

    Driver syntax is compiler, before, absolute sources, -o, absolute output,
    after. Caller supplies ABI/header/link settings. No translation, tool fallback
    or retry occurs. Nonzero exits are data; launch/time-limit failures raise.
    """
    argv = [compiler, *before, *(str(_Path(path).resolve()) for path in sources),
            "-o", str(_Path(output).resolve()), *after]
    return run_command(argv, product_dir=product_dir, env=env, timeout=timeout)


@_dataclasses.dataclass(frozen=True)
class Observation:
    """Value, original exception/traceback and Python text streams from one operation.

    exception=None means success, even if value=None. Failures are not classified
    as acceptable rejections. There is no process exit status. Native descriptor
    output and potentially hanging work require the bounded subprocess driver.
    """
    value: object
    exception: object
    traceback: object
    stdout: str
    stderr: str

    def reraise(self):
        """Return value on success; otherwise raise the original error with traceback."""
        if self.exception is not None:
            raise self.exception.with_traceback(self.traceback)
        return self.value

    def format_traceback(self):
        """Return full traceback text, or empty text on success; retain cause chains."""
        if self.exception is None:
            return ""
        return "".join(_traceback.format_exception(type(self.exception), self.exception,
                                                   self.traceback))


def observe(call, *, consume=None):
    """Return Observation for a call and explicit consumer within one capture scope.

    consume receives the call result; its result becomes the observed value. This
    supports caller-defined generator/async driving without implicit consumption.
    Exceptions from either phase are preserved, not declared product rejections;
    unexpected errors must be reraised by callers. SystemExit/KeyboardInterrupt
    and instrumentation failures propagate. No in-process preemption is offered:
    potentially blocking operations belong in run_python with a finite timeout.
    """
    out, err = _io.StringIO(), _io.StringIO()
    value = exception = tb = None
    with _contextlib.redirect_stdout(out), _contextlib.redirect_stderr(err):
        try:
            value = call()
            if consume is not None:
                value = consume(value)
        except Exception as cause:
            value, exception, tb = None, cause, cause.__traceback__
    return Observation(value, exception, tb, out.getvalue(), err.getvalue())


def parse_json(data):
    """Return the complete parsed JSON document; malformed data raises.

    No log stripping/field guessing occurs; command status is not inspected.
    """
    return _json.loads(data)


@_dataclasses.dataclass
class HTMLNode:
    """HTML tag, ordered attributes and mixed text/element content, without meanings.

    parse_html returns a synthetic document root. No exit status is represented.
    """
    tag: str
    attrs: tuple = ()
    content: list = _dataclasses.field(default_factory=list)

    def text(self):
        """Return descendant text in document order without guessing layout/labels."""
        return "".join(item.text() if isinstance(item, HTMLNode) else item
                       for item in self.content)

    def elements(self, tag=None):
        """Yield descendant elements in order, optionally by exact tag; absence is empty."""
        for item in self.content:
            if isinstance(item, HTMLNode):
                if tag is None or item.tag == tag:
                    yield item
                yield from item.elements(tag)


class _HTMLReader(_html.HTMLParser):
    _void = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = HTMLNode("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = HTMLNode(tag, tuple(attrs))
        self.stack[-1].content.append(node)
        if tag not in self._void:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].content.append(HTMLNode(tag, tuple(attrs)))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].content.append(data)


def parse_html(data):
    """Return an HTMLNode document through the standard HTML parser.

    Bytes decode strictly as UTF-8; callers decode other charsets explicitly.
    Standard permissive HTML parsing applies; no product-specific fields/repairs
    are inferred. Decode/parser failures raise; no command status is interpreted.
    """
    parser = _HTMLReader()
    parser.feed(data.decode("utf-8") if isinstance(data, bytes) else data)
    parser.close()
    return parser.root


def parse_xml(data):
    """Return the XML root; malformed XML raises ParseError.

    Byte encoding follows XML declarations. Fields and status are not interpreted.
    """
    return _xml.fromstring(data)


@_dataclasses.dataclass(frozen=True)
class DependencyRule:
    """Absolute target/prerequisite Path tuples for one Make dependency rule.

    No existence/regeneration assertion or product exit status is implied.
    """
    targets: tuple
    prerequisites: tuple


def parse_make_dependencies(data, *, base):
    """Return DependencyRule tuples, resolving literal paths against explicit base.

    Supports multiple targets/rules, empty prerequisites, comments, escaped
    whitespace/#/:/backslash, doubled dollars and continued lines. Variables,
    recipes and unsupported Make syntax raise rather than being evaluated or
    silently misread. Invalid UTF-8 raises. No status/file existence is inferred.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    data = data.replace("\r\n", "\n")
    lines, current = [], []
    index = 0
    while index < len(data):
        char = data[index]
        if char == "\\" and index + 1 < len(data) and data[index + 1] == "\n":
            current.append(" ")
            index += 2
        elif char == "\n":
            lines.append("".join(current))
            current = []
            index += 1
        else:
            current.append(char)
            index += 1
    if current:
        lines.append("".join(current))
    root = _Path(base).resolve(strict=True)
    rules = []
    for line in lines:
        if line.startswith("\t") and line.strip():
            raise ValueError("Make recipes are not dependency records")
        sides, side, token, index = [[], []], 0, [], 0
        def flush():
            if token:
                sides[side].append("".join(token))
                token.clear()
        while index < len(line):
            char = line[index]
            if char == "\\":
                if index + 1 == len(line):
                    raise ValueError("Trailing dependency escape")
                following = line[index + 1]
                if following in " \t#:\\;|=*?[]%":
                    token.append(following)
                    index += 2
                    continue
                token.append(char)
            elif char == "$":
                if index + 1 >= len(line) or line[index + 1] != "$":
                    raise ValueError("Make variable expansion is unsupported")
                token.append("$")
                index += 2
                continue
            elif char == "#":
                break
            elif char.isspace():
                flush()
            elif char == ":":
                if side:
                    raise ValueError("Unescaped colon in prerequisites")
                flush()
                side = 1
            elif char in ";|=*?[]%":
                raise ValueError(f"Unsupported Make syntax: {char}")
            else:
                token.append(char)
            index += 1
        flush()
        if not sides[0] and not sides[1] and side == 0:
            continue
        if side != 1 or not sides[0]:
            raise ValueError("Dependency rule requires targets and colon")
        rules.append(DependencyRule(tuple((root / name).resolve() for name in sides[0]),
                                    tuple((root / name).resolve() for name in sides[1])))
    return tuple(rules)
