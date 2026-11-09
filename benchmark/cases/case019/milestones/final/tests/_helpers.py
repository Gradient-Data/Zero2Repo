# feature: F00
"""Shared driving machinery; no product imports, expectations, or test cases.

Commands preserve nonzero exit statuses. Infrastructure, timeout, observation,
and installation failures raise; none mean that a product capability is absent.
PDF observations use PyMuPDF as an independent consumer, in a bounded process.
All paths and entry points are supplied by callers. No parent environment is
modified. Callers own assertions and any interpretation of product diagnostics.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import multiprocessing as _multiprocessing
import os as _os
import pathlib as _pathlib
import pickle as _pickle
import signal as _signal
import socketserver as _socketserver
import ssl as _ssl
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import traceback as _traceback
import urllib.request as _request
import warnings as _warnings


class MachineryError(RuntimeError):
    """Driving/observation failure, never a product answer; cause is chained."""


class ExecutionTimeout(MachineryError):
    """Bounded execution expired; partial command output is on ``result``."""

    def __init__(self, message, result=None):
        """Return an exception carrying partial output, without a success code."""
        super().__init__(message)
        self.result = result


class PreconditionError(MachineryError):
    """A real external prerequisite failed; never represents a skip or pass."""


@_dataclasses.dataclass(frozen=True)
class CommandResult:
    """Raw command result: argv, status, and byte streams; None status is timeout.

    A nonzero status is a product/process result, not an automatic assertion.
    Streams are bytes to avoid losing diagnostics to an encoding assumption.
    """

    argv: tuple
    returncode: object
    stdout: bytes
    stderr: bytes


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Completed public call: value or original exception, text streams, warnings.

    ``exception`` is None on return; otherwise value is None and traceback holds
    the original formatted traceback. Warning entries retain category, message,
    filename and line number. Infrastructure failures raise instead of returning.
    """

    value: object
    exception: object
    traceback: object
    stdout: str
    stderr: str
    warnings: tuple


@_dataclasses.dataclass(frozen=True)
class Workspace:
    """Isolated paths and child environment; no process exit status is implied.

    ``work`` and ``output`` are separate directories. ``env`` is a complete child
    environment with private home/cache/temp locations; the parent is unchanged.
    """

    root: _pathlib.Path
    work: _pathlib.Path
    output: _pathlib.Path
    env: dict


@_dataclasses.dataclass(frozen=True)
class PythonEnvironment:
    """A private venv's interpreter, scripts directory and child environment.

    Creation errors raise; existence of this record does not imply the product
    or any additional distributions have been installed.
    """

    root: _pathlib.Path
    python: _pathlib.Path
    scripts: _pathlib.Path
    env: dict


def _bound(timeout):
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    return timeout


def _kill_group(pid):
    try:
        _os.killpg(pid, _signal.SIGKILL)
    except ProcessLookupError:
        pass  # The process group already exited.


def run_command(command, *, cwd=None, env=None, input=None, timeout=60,
                network_prefix=()):
    """Return CommandResult for an argv sequence, with no shell or status check.

    ``input`` is bytes (or None, which closes stdin). ``env`` is a complete child
    environment; None inherits the parent. A caller-provided network isolation
    prefix may wrap the command. Launch errors raise MachineryError with cause;
    expiry kills the owned process group and raises ExecutionTimeout with output.
    """
    _bound(timeout)
    if isinstance(command, (str, bytes)) or not command:
        raise ValueError('command must be a nonempty argv sequence')
    if input is not None and not isinstance(input, bytes):
        raise TypeError('input must be bytes or None')
    argv = tuple(_os.fspath(part) for part in (*network_prefix, *command))
    try:
        process = _subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=_subprocess.PIPE,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            start_new_session=True)
    except OSError as exc:
        raise MachineryError('Cannot launch {!r}'.format(argv)) from exc
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except _subprocess.TimeoutExpired as exc:
        _kill_group(process.pid)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except _subprocess.TimeoutExpired as cleanup:
            process.stdout.close()
            process.stderr.close()
            raise ExecutionTimeout('Process cleanup exceeded five seconds',
                                   CommandResult(argv, None, exc.output or b'',
                                                 exc.stderr or b'')) from cleanup
        raise ExecutionTimeout('Command exceeded {} seconds'.format(timeout),
                               CommandResult(argv, None, stdout, stderr)) from exc
    except BaseException:
        _kill_group(process.pid)
        process.wait(timeout=5)
        raise
    return CommandResult(argv, process.returncode, stdout, stderr)


def run_python(source, *, python=None, args=(), **options):
    """Run caller's Python source; return raw CommandResult, including traceback.

    Use plain public imports in source. ``python`` selects an interpreter; None
    uses this suite's interpreter. All run_command input/error semantics apply.
    Values to inspect can be explicitly serialized by the caller's source.
    """
    return run_command((python or _sys.executable, '-c', source, *args), **options)


def run_cli(entrypoint, args=(), **options):
    """Run a public CLI argv prefix plus arguments; return raw CommandResult.

    Entry point is a nonempty sequence, e.g. a binary or interpreter/module argv.
    Nonzero statuses remain results; launch errors and timeouts raise.
    """
    if isinstance(entrypoint, (str, bytes)):
        raise TypeError('entrypoint must be an argv sequence')
    return run_command((*entrypoint, *args), **options)


def run_sphinx(entrypoint, source, output, *, builder, args=(), **options):
    """Run the public Sphinx CLI with explicit builder and directories.

    Return CommandResult without interpreting status, reports or output files.
    Launch errors/timeouts raise as in run_command; extra arguments are verbatim.
    """
    return run_cli(entrypoint, ('-b', builder, *args, _os.fspath(source),
                                _os.fspath(output)), **options)


def _call_worker(destination, function, args, kwargs, consume, cwd, env):
    _os.setsid()
    if cwd is not None:
        _os.chdir(cwd)
    if env is not None:
        _os.environ.clear()
        _os.environ.update(env)
    with open(destination / 'stdout', 'wb', buffering=0) as stdout, \
            open(destination / 'stderr', 'wb', buffering=0) as stderr:
        _os.dup2(stdout.fileno(), 1)
        _os.dup2(stderr.fileno(), 2)
        # Replace Python streams too, so pytest capture cannot divert them.
        _sys.stdout = _io.TextIOWrapper(_os.fdopen(_os.dup(1), 'wb'),
                                        encoding='utf-8', write_through=True)
        _sys.stderr = _io.TextIOWrapper(_os.fdopen(_os.dup(2), 'wb'),
                                        encoding='utf-8', write_through=True)
        value, exception, trace = None, None, None
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter('always')
            try:
                value = function(*args, **kwargs)
                if consume is not None:
                    value = consume(value)
            except BaseException as exc:
                exception = exc
                trace = _traceback.format_exc()
            records = tuple((item.category, item.message, item.filename,
                             item.lineno) for item in caught)
        _sys.stdout.flush()
        _sys.stderr.flush()
        # Serialization failures deliberately escape as worker failures.
        with open(destination / 'result', 'wb') as stream:
            _pickle.dump((value, exception, trace, records), stream)


def call_public(function, *args, kwargs=None, consume=None, cwd=None, env=None,
                timeout=60):
    """Call a caller-supplied public callable in a bounded Linux fork worker.

    Return CallResult with value/original product exception, diagnostics and
    warnings. ``consume`` optionally fully materializes a lazy public result in
    that worker (e.g. list); its errors are retained as call exceptions. Without
    it the returned value must already be serializable. Side effects on parent
    objects do not propagate. Use run_python for fresh-import/cache experiments.
    Worker/setup/serialization errors raise MachineryError; expiry raises
    ExecutionTimeout. No product symbol is looked up or imported by this helper.
    """
    _bound(timeout)
    with _tempfile.TemporaryDirectory(prefix='suite-call-') as temporary:
        destination = _pathlib.Path(temporary)
        process = _multiprocessing.get_context('fork').Process(
            target=_call_worker,
            args=(destination, function, args, kwargs or {}, consume, cwd, env))
        process.start()
        try:
            process.join(timeout)
            if process.is_alive():
                # setsid may not yet have run if the worker could not be scheduled.
                if _os.getpgid(process.pid) == process.pid:
                    _kill_group(process.pid)
                else:
                    process.kill()
                process.join(5)
                raise ExecutionTimeout('Public call exceeded {} seconds'.format(timeout))
            stdout = (destination / 'stdout').read_text(encoding='utf-8')
            stderr = (destination / 'stderr').read_text(encoding='utf-8')
            if process.exitcode != 0:
                raise MachineryError('Call worker exited {}\n{}'.format(
                    process.exitcode, stderr))
            try:
                with open(destination / 'result', 'rb') as stream:
                    value, exception, trace, records = _pickle.load(stream)
            except Exception as exc:
                raise MachineryError('Cannot read call worker result') from exc
            return CallResult(value, exception, trace, stdout, stderr, records)
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            process.close()


@_contextlib.contextmanager
def isolated_workspace(*, parent=None, env=None):
    """Yield Workspace with fresh work/output/home/cache/temp, then remove it.

    The parent process environment is untouched. Pass the yielded complete env
    explicitly to commands. Setup/cleanup filesystem failures propagate; no exit
    status or product outcome is synthesized. Reuse only for intentional caching.
    """
    with _tempfile.TemporaryDirectory(prefix='suite-', dir=parent) as temporary:
        root = _pathlib.Path(temporary)
        for name in ('work', 'output', 'home', 'cache', 'config', 'data', 'tmp'):
            (root / name).mkdir()
        child_env = dict(_os.environ if env is None else env)
        child_env.update(HOME=str(root / 'home'),
                         XDG_CACHE_HOME=str(root / 'cache'),
                         XDG_CONFIG_HOME=str(root / 'config'),
                         XDG_DATA_HOME=str(root / 'data'),
                         TMPDIR=str(root / 'tmp'), PYTHONNOUSERSITE='1')
        yield Workspace(root, root / 'work', root / 'output', child_env)


def write_text(path, text):
    """Write UTF-8 text verbatim and return Path; filesystem/encoding errors raise.

    Create parent directories but never infer product configuration or content.
    There is no product exit status.
    """
    path = _pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def text_stream(text):
    """Return a new StringIO input stream; invalid text raises, no exit status."""
    return _io.StringIO(text)


def create_python_environment(path, *, python=None, env=None, timeout=120):
    """Create a fresh private venv and return PythonEnvironment.

    No system packages are inherited or installed. Existing destination is an
    error. Creation failure raises MachineryError containing command diagnostics;
    launch/timeout errors propagate. Caller owns eventual directory cleanup.
    """
    path = _pathlib.Path(path).absolute()
    path.mkdir(parents=True, exist_ok=False)
    result = run_command((python or _sys.executable, '-m', 'venv', str(path)),
                         env=env, timeout=timeout)
    _require_tool_success(result, 'Virtual environment creation')
    scripts = path / 'bin'
    child_env = dict(_os.environ if env is None else env)
    child_env.update(VIRTUAL_ENV=str(path), PYTHONNOUSERSITE='1',
                     PATH=str(scripts) + _os.pathsep + child_env.get('PATH', ''))
    child_env.pop('PYTHONHOME', None)
    child_env.pop('PYTHONPATH', None)
    return PythonEnvironment(path, scripts / 'python', scripts, child_env)


def _require_tool_success(result, operation):
    if result.returncode != 0:
        error = MachineryError('{} failed: {!r}'.format(operation, result))
        error.result = result
        raise error


def install_distributions(environment, requirements, *, args=(), timeout=180,
                          network_prefix=()):
    """Install real requirements into the supplied private venv; return result.

    No requirements are invented and no global/user installation is used.
    Failure raises MachineryError with ``result`` containing original pip output;
    launch/timeout errors propagate. Network policy is explicitly supplied.
    """
    if isinstance(requirements, (str, bytes)) or not requirements:
        raise ValueError('requirements must be a nonempty sequence')
    result = run_command((environment.python, '-m', 'pip', '--isolated',
                          'install', *args, *requirements), env=environment.env,
                         timeout=timeout, network_prefix=network_prefix)
    _require_tool_success(result, 'Distribution installation')
    return result


def installed_distributions(python, *, env=None, timeout=30):
    """Return independent distribution metadata records, not product listings.

    Each record contains name, version and declared entry points. A bounded
    interpreter uses standard importlib.metadata, never product imports. Tool or
    JSON decoding errors raise; a legitimate empty installation returns a list.
    """
    source = """import importlib.metadata as metadata
import json
print(json.dumps([{'name': d.metadata['Name'], 'version': d.version,
                   'entry_points': [{'group': e.group, 'name': e.name,
                                     'value': e.value} for e in d.entry_points]}
                  for d in metadata.distributions()]))
"""
    result = run_python(source, python=python, env=env, timeout=timeout)
    _require_tool_success(result, 'Distribution inventory')
    return _json.loads(result.stdout)


def network_isolation_prefix(entrypoint, *, env=None, timeout=10):
    """Probe real network-namespace isolation; return a usable argv prefix.

    ``entrypoint`` is the caller-selected unshare executable argv prefix. The
    probe must succeed before any product invocation. Missing tools/permissions
    raise MachineryError, never masquerading as offline product behavior. This
    does not change the host network or replace network calls with fake results.
    """
    if isinstance(entrypoint, (str, bytes)) or not entrypoint:
        raise ValueError('entrypoint must be a nonempty argv sequence')
    prefix = (*entrypoint, '--net', '--')
    result = run_command((*prefix, _sys.executable, '-c', 'pass'),
                         env=env, timeout=timeout)
    _require_tool_success(result, 'Network namespace probe')
    return prefix


def fetch_bytes(url, *, python=None, env=None, timeout=30):
    """Fetch a real URL in a bounded child; return response body bytes.

    No cache or fabricated answer is used. URL/tool failure raises
    PreconditionError with original diagnostics on ``result``; launch and timeout
    errors propagate. This establishes reachability only, not product behavior.
    """
    source = """import sys
import urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=float(sys.argv[2])) as response:
    sys.stdout.buffer.write(response.read())
"""
    result = run_python(source, python=python, args=(url, str(timeout)),
                        env=env, timeout=timeout)
    if result.returncode != 0:
        error = PreconditionError('Real URL fetch failed: {!r}'.format(result))
        error.result = result
        raise error
    return result.stdout



@_dataclasses.dataclass(frozen=True)
class Mirror:
    """A running loopback HTTPS mirror: child environment and request log.

    ``env`` is a complete child environment whose HTTPS proxy is the mirror and
    whose trusted certificate authority is the suite's test authority.
    ``requests`` lists each requested ``https://host/path?query`` in order.
    """

    env: dict
    requests: list


_ASSETS = _pathlib.Path(__file__).with_name('assets')
_SERVICE_CA = _ASSETS / 'F00_service_ca.pem'
_SERVICE_IDENTITY = _ASSETS / 'F00_service_identity.pem'


class _MirrorServer(_socketserver.ThreadingMixIn, _socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _read_head(stream):
    line = stream.readline(65537)
    if not line:
        return None, {}
    headers = {}
    while True:
        header = stream.readline(65537)
        if header in (b'\r\n', b'\n', b''):
            break
        name, _, value = header.decode('latin-1').partition(':')
        headers[name.strip().lower()] = value.strip()
    return line.decode('latin-1').split(), headers


def _mirror_handler(answer, log, context):
    class Handler(_socketserver.StreamRequestHandler):
        timeout = 60

        def _respond(self, stream, status, body, content_type):
            stream.write('HTTP/1.1 {} {}\r\nContent-Type: {}\r\n'
                         'Content-Length: {}\r\nConnection: close\r\n\r\n'
                         .format(status, 'Mirror', content_type, len(body))
                         .encode('latin-1') + body)
            stream.flush()

        def handle(self):
            request, _ = _read_head(self.rfile)
            if not request or request[0] != 'CONNECT':
                self._respond(self.wfile, 405, b'', 'text/plain')
                return
            host = request[1].rsplit(':', 1)[0]
            self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            self.wfile.flush()
            try:
                tunnel = context.wrap_socket(self.connection, server_side=True)
            except (_ssl.SSLError, OSError):
                return  # The client refused the test authority.
            with tunnel, tunnel.makefile('rwb') as stream:
                request, headers = _read_head(stream)
                if not request:
                    return
                if int(headers.get('content-length') or 0):
                    stream.read(int(headers['content-length']))
                url = 'https://' + host + request[1]
                log.append(url)
                status, body, content_type = answer(url) or (
                    404, b'Not Found', 'text/plain')
                self._respond(stream, status,
                              b'' if request[0] == 'HEAD' else body,
                              content_type)
    return Handler


@_contextlib.contextmanager
def loopback_https_mirror(answer, *, env=None):
    """Yield Mirror answering HTTPS requests to real service hosts, then stop.

    ``answer(url)`` returns ``(status, body_bytes, content_type)`` for a full
    ``https://host/path?query`` URL, or None for a 404. The mirror is a local
    CONNECT proxy presenting the suite's test identity; nothing reaches the
    real network. Children see it through the standard proxy and certificate
    variables in ``Mirror.env``; the parent environment is unchanged.
    """
    context = _ssl.create_default_context(_ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(_SERVICE_IDENTITY)
    log = []
    server = _MirrorServer(('127.0.0.1', 0), _mirror_handler(answer, log, context))
    thread = _threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proxy = 'http://127.0.0.1:{}'.format(server.server_address[1])
        child_env = dict(_os.environ if env is None else env)
        for name in ('NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy'):
            child_env.pop(name, None)
        child_env.update(HTTPS_PROXY=proxy, https_proxy=proxy,
                         HTTP_PROXY=proxy, http_proxy=proxy,
                         SSL_CERT_FILE=str(_SERVICE_CA),
                         REQUESTS_CA_BUNDLE=str(_SERVICE_CA),
                         PIP_CERT=str(_SERVICE_CA))
        yield Mirror(child_env, log)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

_PDF_SOURCE = r"""
import base64
import json
import sys
import fitz


def encode(value):
    if isinstance(value, bytes):
        return {'encoding': 'base64', 'data': base64.b64encode(value).decode('ascii')}
    if isinstance(value, (fitz.Rect, fitz.IRect, fitz.Point, fitz.Matrix, fitz.Quad)):
        return list(value)
    raise TypeError('Cannot serialize PDF observation: ' + type(value).__name__)


with fitz.open(sys.argv[1]) as document:
    if not document.is_pdf:
        raise ValueError('Input is not a PDF')
    if document.needs_pass:
        raise ValueError('PDF needs a password')
    if document.is_repaired:
        raise ValueError('PDF parser had to repair damaged input')
    if sys.argv[2] == 'observe':
        pages = []
        for page in document:
            pages.append({'rect': list(page.rect), 'rotation': page.rotation,
                          'text': page.get_text('text', sort=False),
                          'raw_text': page.get_text('rawdict', sort=False),
                          'glyphs': page.get_texttrace(),
                          'images': page.get_image_info(),
                          'drawings': page.get_drawings(),
                          'links': page.get_links(),
                          'fonts': page.get_fonts(full=True)})
        result = {'metadata': document.metadata,
                  'outline': document.get_toc(simple=False), 'pages': pages}
        print(json.dumps(result, default=encode, allow_nan=False))
    elif sys.argv[2] == 'raster':
        page = document.load_page(int(sys.argv[3]))
        scale = float(sys.argv[4]) / 72
        page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                        alpha=bool(int(sys.argv[5]))).save(sys.argv[6])
    else:
        raise ValueError('Unknown PDF observation operation')
"""


def observe_pdf(path, *, python=None, env=None, timeout=60):
    """Return a parsed PDF snapshot from independent PyMuPDF, in page order.

    The dict has metadata, outline and pages. Each page exposes rect, rotation,
    extracted text, raw text positions, glyph traces, images, drawings, links and
    font records using the observer's documented schemas. Coordinates are the
    observer's page coordinates in points; no layout inference is performed.
    Binary fields are explicitly base64-tagged. Valid absent fields stay absent.
    Missing observer, damaged/encrypted PDF, extraction or serialization errors
    raise MachineryError with original diagnostics; timeout errors propagate.
    """
    result = run_python(_PDF_SOURCE, python=python,
                        args=(_os.fspath(path), 'observe'), env=env,
                        timeout=timeout)
    _require_tool_success(result, 'PDF observation')
    return _json.loads(result.stdout)


def rasterize_pdf_page(path, destination, *, page=0, dpi=144, alpha=True,
                       python=None, env=None, timeout=60):
    """Render a zero-based PDF page to caller's PNG path; return that Path.

    Uses independent PyMuPDF without comparing pixels or asserting appearance.
    Explicit dpi must be finite and positive. Observer/file/page errors raise
    MachineryError with diagnostics; timeouts propagate. Parent must exist.
    """
    _bound(dpi)
    result = run_python(_PDF_SOURCE, python=python,
                        args=(_os.fspath(path), 'raster', str(page), str(dpi),
                              str(int(alpha)), _os.fspath(destination)),
                        env=env, timeout=timeout)
    _require_tool_success(result, 'PDF rasterization')
    return _pathlib.Path(destination)
