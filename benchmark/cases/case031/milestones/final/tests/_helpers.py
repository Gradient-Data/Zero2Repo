# feature: F00
"""Shared public-interface drivers without feature expectations.

Tests import public product symbols with plain imports and pass them here,
including constructors, bound add methods and setters. Inputs, result schemas,
diagnostic fields and feature expectations belong to callers. No product layout
or example data is inferred. In-process capture is serial and main-thread only;
use run_command for isolation and potentially blocking native code.
"""

import collections.abc as _abc
import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import logging as _logging
import os as _os
from pathlib import Path as _Path
import subprocess as _subprocess
import tempfile as _tempfile

__all__ = [
    "CallResult", "invoke", "run_command", "read_fields", "read_table",
    "temporary_environment", "temporary_directory",
]


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Observations from one completed in-process invocation; no OS exit status.

    value is the returned value or reader result. exception is None or the
    original explicitly expected product exception, retaining its traceback.
    stdout/stderr are Python stream text; logs is a tuple of original LogRecords
    including structured extra fields. Unknown errors and read errors
    raise rather than returning an answer.
    """

    value: object
    exception: BaseException | None
    stdout: str
    stderr: str
    logs: tuple



class _Recorder(_logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@_contextlib.contextmanager
def _logs(logger, level):
    handler = _Recorder()
    old_level = logger.level
    logger.addHandler(handler)
    try:
        logger.setLevel(level)
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        handler.close()


def invoke(entry_point, *args, kwargs=None, reader=None,
           expected_exceptions=(), logger=None, log_level=_logging.DEBUG):
    """Return CallResult from a supplied public callable and optional reader.

    args/kwargs pass unchanged to the callable. Returned iterators are fully
    consumed into lists. reader(value) then selects/loads
    public results inside the same capture; it must fully load
    any other lazy outputs using documented fields and actual format parsers.

    Only explicitly listed expected_exceptions from invocation or iterator
    consumption are recorded. Reader errors and unknown exceptions always
    propagate with original tracebacks. No product status or diagnostic content
    is interpreted. logger is a supplied logging.Logger; None captures records
    reaching the root. Existing handlers remain attached, levels are restored,
    and explicitly disabled loggers are not re-enabled.

    Python stream capture excludes native file-descriptor writes. Runtime limits
    belong to the surrounding execution harness, not to a product assertion.
    """
    if not isinstance(expected_exceptions, tuple) or any(
        not isinstance(cls, type) or not issubclass(cls, Exception)
        for cls in expected_exceptions
    ):
        raise TypeError("expected_exceptions must be a tuple of Exception classes")
    output, errors = _io.StringIO(), _io.StringIO()
    target_logger = _logging.getLogger() if logger is None else logger
    value, exception = None, None
    with _logs(target_logger, log_level) as records:
        with _contextlib.redirect_stdout(output), _contextlib.redirect_stderr(errors):
            try:
                value = entry_point(*args, **({} if kwargs is None else kwargs))
                if isinstance(value, _abc.Iterator):
                    value = list(value)
            except expected_exceptions as exc:
                exception = exc
            if exception is None and reader is not None:
                value = reader(value)
                if isinstance(value, _abc.Iterator):
                    value = list(value)
    return CallResult(value, exception, output.getvalue(), errors.getvalue(),
                      tuple(records))


def run_command(command, *, cwd=None, env=None, input_text=None,
                encoding="utf-8"):
    """Return CompletedProcess with integer returncode and captured text streams.

    command is an explicit nonempty argument sequence, never shell text. None
    cwd uses the harness product directory. env overrides inherited variables;
    None values remove keys. input_text is fed to stdin, closed even when absent.
    Nonzero exits are returned unchanged, including negative signal statuses.
    Launch/decoding errors propagate. Runtime containment is provided by the
    surrounding execution harness. Callers must not launch detached/background
    workers through this driver.
    """
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argument sequence, not shell text")
    arguments = tuple(command)
    if not arguments:
        raise ValueError("command must not be empty")
    environment = _os.environ.copy()
    if env is not None:
        for name, value in env.items():
            if value is None:
                environment.pop(name, None)
            else:
                environment[name] = value
    return _subprocess.run(
        arguments, cwd=cwd, env=environment, input=input_text,
        stdin=_subprocess.DEVNULL if input_text is None else None,
        capture_output=True, text=True, encoding=encoding, check=False,
    )


def read_fields(obj, *names):
    """Return a dict of explicitly named public attributes, without interpretation.

    Names are single attributes, not dotted paths. Read nested public children
    explicitly in successive calls. Missing fields and property errors propagate;
    private names raise ValueError. Values are not copied or substituted. No exit
    status is applicable.
    """
    result = {}
    for name in names:
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ValueError("Expected a single public attribute name")
        result[name] = getattr(obj, name)
    return result


def read_table(table, *, rows=None, columns=None):
    """Return a detached copy selected through a public labeled table's loc.

    rows/columns are explicit label selectors; None retains that axis. There is
    no positional selection, sorting, missing-label substitution or implicit
    alignment. Missing labels, unsupported table types and copy/read errors
    propagate. No exit status is applicable. Targets two-dimensional tables.
    """
    return table.loc[
        slice(None) if rows is None else rows,
        slice(None) if columns is None else columns,
    ].copy(deep=True)


@_contextlib.contextmanager
def temporary_environment(changes):
    """Yield None with environment changes; restore touched keys on exit.

    Strings set keys and None removes them. Body and restoration errors propagate;
    no exit status is applicable. Changes are process-global: use serially.
    Unmentioned keys are neither changed nor restored.
    """
    original = {name: _os.environ.get(name) for name in changes}
    try:
        for name, value in changes.items():
            if value is None:
                _os.environ.pop(name, None)
            else:
                _os.environ[name] = value
        yield
    finally:
        for name, value in original.items():
            if value is None:
                _os.environ.pop(name, None)
            else:
                _os.environ[name] = value


@_contextlib.contextmanager
def temporary_directory(*, parent=None, prefix="suite-"):
    """Yield a fresh pathlib.Path and remove its contents on context exit.

    parent/prefix are caller-selected filesystem parameters. Creation, body and
    cleanup errors propagate; no exit status is applicable. The working directory
    is unchanged and no product files are inferred.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as directory:
        yield _Path(directory)


def isolated_site(directory, *, excluded, product_spec):
    """Expose installed dependencies except named optional packages to a child.

    The caller supplies the selected product's import spec. The child uses -S
    and this directory as its sole third-party import root; no modules or
    dependency-discovery functions are replaced.
    """
    import sysconfig

    directory.mkdir()
    omitted = set(excluded)
    for entry in _Path(sysconfig.get_path('purelib')).iterdir():
        if entry.name in {'velmora', 'velmora.py'}:
            continue
        if any(entry.name == name or entry.name.startswith(name + '-')
               or entry.name.startswith(name + '.') for name in omitted):
            continue
        (directory / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    source = _Path(product_spec.origin)
    if product_spec.submodule_search_locations is not None:
        (directory / 'velmora').symlink_to(source.parent, target_is_directory=True)
    else:
        (directory / 'velmora.py').symlink_to(source)
    return directory
