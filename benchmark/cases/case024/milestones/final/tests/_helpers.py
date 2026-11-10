# feature: F00
"""Shared mechanics only: callers supply public entry points and expectations.

Python capture redirects Python streams, not native file descriptors. Use a
subprocess for OS-level capture and fresh interpreter state. Author modules
written in a workspace are normally importable by Python launched there; this
module never changes sys.path. Repository paths remain explicit caller inputs.
The adjacent pytest conftest contains each complete node in a worker process,
so leaked product threads cannot outlive a reported invocation failure.
"""

import collections.abc as _abc
import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import os as _os
import pathlib as _pathlib
import shlex as _shlex
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Return value, captured streams, original exception and SystemExit status.

    Normal calls have exception=None and exit_code=None. Failed calls have
    value=None and the original exception with its traceback and cause intact.
    Only SystemExit sets exit_code: None maps to 0, integers stay unchanged,
    other codes map to 1. Its original code remains on exception.code.
    """

    value: object
    stdout: str
    stderr: str
    exception: object = None
    exit_code: object = None


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Completed argv, integer returncode, stdout and stderr.

    Nonzero statuses, including negative POSIX signal statuses, are data.
    Launch, capture and timeout failures raise instead of returning this object.
    """

    argv: tuple
    returncode: int
    stdout: str
    stderr: str


class InvocationTimeout(AssertionError):
    """Deadline failure with available stdout/stderr, never a product answer.

    There is no completed exit status. Subprocess timeouts retain their original
    exception as the cause.
    """

    def __init__(self, message, stdout='', stderr=''):
        """Create a deadline failure retaining captured output; return None."""
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _seconds(timeout):
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    return timeout


@_contextlib.contextmanager
def _deadline(timeout):
    _seconds(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError('In-process capture requires the main thread')
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError('An existing alarm prevents bounded capture')
    previous = _signal.getsignal(_signal.SIGALRM)

    def expire(signum, frame):
        raise InvocationTimeout('Python invocation exceeded its deadline')

    _signal.signal(_signal.SIGALRM, expire)
    _signal.setitimer(_signal.ITIMER_REAL, timeout)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


@_contextlib.contextmanager
def working_environment(*, cwd=None, env=None):
    """Yield None under temporary cwd/environment overrides, restoring on exit.

    None-valued overrides remove variables; others are inherited. Setup, body
    and restoration errors propagate; no status is synthesized. This changes
    process-global state and must not overlap other in-process invocations.
    """
    previous_dir, previous_env = _os.getcwd(), dict(_os.environ)
    try:
        if env is not None:
            for key, value in env.items():
                if value is None:
                    _os.environ.pop(key, None)
                else:
                    _os.environ[key] = value
        if cwd is not None:
            _os.chdir(cwd)
        yield
    finally:
        _os.chdir(previous_dir)
        _os.environ.clear()
        _os.environ.update(previous_env)


@_contextlib.contextmanager
def workspace(*, parent=None):
    """Yield an absolute temporary Path; remove only that directory on exit.

    Does not initialize repositories or change cwd. I/O and cleanup errors
    propagate; no product status exists. Reuse a repository by passing its
    explicit path to subsequent calls within this context.
    """
    with _tempfile.TemporaryDirectory(dir=parent) as directory:
        yield _pathlib.Path(directory).resolve()


@_contextlib.contextmanager
def candidate_cli_environment():
    """Yield PATH for a scoped CLI using this interpreter and candidate tree.

    No installation is assumed. The executable only enters the public process
    entry point; argv, streams, exceptions and exit status belong to the product.
    It does not expose authored workflow directories on the caller's sys.path.
    Keep this context alive until all launched workers have completed.
    """
    import velnora

    root = str(_pathlib.Path(velnora.__file__).resolve().parent.parent)
    source = (
        'import sys; sys.path.insert(0, {!r}); '
        'sys.argv[0] = "velnora"; from velnora.cli import main; main()'
    ).format(root)
    with _tempfile.TemporaryDirectory(prefix='candidate-cli-') as directory:
        launcher = _pathlib.Path(directory) / 'velnora'
        launcher.write_text(
            '#!/bin/sh\nexec ' + _shlex.quote(_sys.executable) + ' -c '
            + _shlex.quote(source) + ' "$@"\n', encoding='utf-8')
        launcher.chmod(0o755)
        yield {'PATH': _os.pathsep.join([
            directory, str(_pathlib.Path(_sys.executable).parent),
            _os.environ.get('PATH', '')])}


def capture_call(entrypoint, args=(), kwargs=None, *, stdin='', cwd=None,
                 env=None, timeout=60.0):
    """Return CallResult from a supplied public callable, consuming iterators.

    Iterators become lists within the deadline; other values remain unchanged.
    Product Exception/SystemExit, including iteration failures, are recorded.
    KeyboardInterrupt and helper failures raise. Streams are always restored.
    POSIX main-thread alarms bound this call; signal-blocking native work must
    use run_process for an OS-enforced deadline. Capture is not thread-safe.
    """
    out, err, input_stream = _io.StringIO(), _io.StringIO(), _io.StringIO(stdin)
    value, failure, code = None, None, None
    with working_environment(cwd=cwd, env=env):
        with _contextlib.redirect_stdout(out), _contextlib.redirect_stderr(err):
            old_stdin = _sys.stdin
            _sys.stdin = input_stream
            try:
                with _deadline(timeout):
                    try:
                        value = entrypoint(*args, **({} if kwargs is None else kwargs))
                        if isinstance(value, _abc.Iterator):
                            value = list(value)
                    except InvocationTimeout:
                        raise
                    except (Exception, SystemExit) as error:
                        value, failure = None, error
                        if isinstance(error, SystemExit):
                            code = (0 if error.code is None else error.code
                                    if isinstance(error.code, int) else 1)
            except InvocationTimeout as error:
                error.stdout, error.stderr = out.getvalue(), err.getvalue()
                raise
            finally:
                _sys.stdin = old_stdin
    return CallResult(value, out.getvalue(), err.getvalue(), failure, code)


def make_config(config_factory, *, ini):
    """Return configuration from the supplied public factory and exact INI text.

    Factory/read errors propagate; no exit status exists. No backend, executor
    or repository settings are inserted.
    """
    config = config_factory()
    config.read_string(ini)
    return config


def memory_scheduler(sections=None):
    """Construct a public scheduler with an explicit transient repository.

    Callers supply executor or context sections. Persistence tests use their
    own repository configuration instead of this isolated invocation fixture.
    Construction and execution errors belong to the candidate and propagate.
    """
    from velnora import Scheduler
    from velnora.config import Config

    settings = {'backend': {'db_uri': 'sqlite:///:memory:'}}
    if sections is not None:
        settings.update(sections)
    scheduler = Scheduler(config=Config(settings))
    scheduler.load()
    return scheduler


def run_workflow(scheduler, expression, *, run_kwargs=None, **capture_options):
    """Return CallResult from scheduler.run; errors follow capture_call.

    run_kwargs holds product options; capture_options controls invocation.
    Product exceptions/SystemExit are recorded; helper failures raise.
    """
    return capture_call(scheduler.run, (expression,), run_kwargs, **capture_options)


def execute_client(client, argv, **capture_options):
    """Return CallResult from client.execute using full argv including argv[0].

    Supply the public client and all command/repository arguments explicitly.
    Product exceptions/SystemExit are recorded; helper failures raise.
    """
    return capture_call(client.execute, (list(argv),), **capture_options)


def run_process(argv, *, cwd, stdin='', env=None, timeout=60.0):
    """Return ProcessResult for literal argv without a shell, using UTF-8 text.

    env overrides inherited variables; None removes a variable. Nonzero exits
    are data. Launch/encoding/I/O failures raise. Timeout kills only this new
    POSIX process group and raises InvocationTimeout with output and cause.
    Cleanup waits at most five seconds; cleanup failure also raises.
    """
    _seconds(timeout)
    command = tuple(_os.fspath(arg) for arg in argv)
    if not command:
        raise ValueError('argv must not be empty')
    environment = dict(_os.environ)
    if env is not None:
        for key, value in env.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
    process = _subprocess.Popen(
        command, cwd=cwd, env=environment, stdin=_subprocess.PIPE,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
        text=True, encoding='utf-8', start_new_session=True,
    )
    try:
        try:
            out, err = process.communicate(stdin, timeout=timeout)
        except _subprocess.TimeoutExpired as error:
            _os.killpg(process.pid, _signal.SIGKILL)
            out, err = process.communicate(timeout=5.0)
            raise InvocationTimeout(
                'Command exceeded its deadline: {!r}'.format(command), out, err
            ) from error
        return ProcessResult(command, process.returncode, out, err)
    finally:
        if process.poll() is None:
            _os.killpg(process.pid, _signal.SIGKILL)
            process.wait(timeout=5.0)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def run_python(source, *, cwd, python=None, args=(), **process_options):
    """Return ProcessResult for source in a fresh interpreter using -c.

    Uses the current interpreter unless supplied. args follows source in argv.
    Errors/status follow run_process. No import path or pytest state is copied.
    """
    executable = _sys.executable if python is None else python
    return run_process([executable, '-c', source, *args], cwd=cwd, **process_options)


def write_text(path, text):
    """Write UTF-8 text and return its Path, creating missing parents.

    Caller selects the exact filename, including author module or INI filenames.
    Filesystem/encoding errors raise; no product exit status exists.
    """
    target = _pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return target


def write_json(path, value):
    """Write JSON and return its Path; serialization/I/O errors raise.

    Non-finite numbers are rejected. No product status is involved.
    """
    return write_text(path, _json.dumps(value, allow_nan=False))


def write_saved_args(path, args, kwargs, *, serializer):
    """Write (args, kwargs) through the supplied serializer and return its Path.

    serializer takes the pair and a binary stream, like pickle.dump for the
    CLI saved-argument format. Serialization/I/O failures raise; no product
    success or exit status is inferred.
    """
    target = _pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('wb') as stream:
        serializer((args, kwargs), stream)
    return target


def parse_json(text):
    """Return one decoded JSON value; malformed/extra content raises.

    Supply the documented channel. No noise stripping or status inference occurs.
    """
    return _json.loads(text)


def parse_jsonl(text):
    """Return JSON values decoded from every line in order.

    Empty input returns []; blank/malformed lines raise. A trailing newline is
    allowed. No lines are filtered and no exit status is inferred.
    """
    return [parse_json(line) for line in text.splitlines()]


def read_log_json(text):
    """Return records from the log JSON channel's JSON Lines text.

    Parse errors raise. No fields are guessed; invocation status is separate.
    """
    return parse_jsonl(text)


def read_export_jsonl(path):
    """Return records from the exact export JSON Lines file supplied by caller.

    File/parse errors raise; invocation status is read separately.
    """
    return parse_jsonl(_pathlib.Path(path).read_text(encoding='utf-8'))


def index_records(records, *, key):
    """Return an identifier-to-record dict using an explicit public key accessor.

    key(record) returns a hashable identifier, optionally qualified by type.
    Duplicate keys raise ValueError; missing fields/accessor failures propagate.
    No record shape, identifier algorithm or product status is assumed.
    """
    result = {}
    for record in records:
        identifier = key(record)
        if identifier in result:
            raise ValueError('Duplicate record key: {!r}'.format(identifier))
        result[identifier] = record
    return result


def resolve_record(index, identifier):
    """Return the record with this exact identifier from the caller's index.

    Missing/unhashable keys raise KeyError/TypeError, never a fabricated product
    missing-record result. No fuzzy matching or status inference occurs.
    """
    return index[identifier]
