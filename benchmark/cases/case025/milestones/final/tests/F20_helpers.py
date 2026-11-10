# feature: F20
"""Source-editing observations through the CLI and a real controlling terminal."""
import ast
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import signal
import struct
import sys
import termios
import time
import types
import typing

from _helpers import read_json
from F01_helpers import check_source, concise_headers, plain_stderr


def edit_report(root, flags=()):
    if '--autofix' in flags:
        result = check_source(root, ['--output-format', 'concise', *flags, str(root / 'sample.py')])
        assert result.returncode == 1, result
        headers = concise_headers(plain_stderr(result))
        assert headers, result
        return [{'code': header[4]} for header in headers]
    report = root / 'edits.json'
    if report.exists():
        report.unlink()
    result = check_source(root, ['--json-output', str(report), *flags, str(root / 'sample.py')])
    if result.returncode == 0:
        assert result.stderr == '', result
        return []
    findings = read_json(report, result=result)
    assert isinstance(findings, list), findings
    assert result.returncode == int(bool(findings)), result
    if findings:
        assert result.stderr.strip(), result
    return findings


def terminal_edit(root, flags, answer):
    search = str(Path.cwd()) + os.pathsep + os.environ.get('PYTHONPATH', '')
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(root)
        os.environ['PYTHONPATH'] = search
        os.environ['TERM'] = 'xterm'
        os.execv(sys.executable, [sys.executable, '-m', 'velnora', '-f', *flags,
                                 str(root / 'sample.py')])
    transcript = bytearray()
    answered = False
    reaped = False
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], min(0.2, max(0, deadline - time.monotonic())))
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                break
            if not chunk:
                break
            transcript.extend(chunk)
            if not answered and b'Accept change (' in transcript:
                os.write(fd, (answer + '\n').encode('ascii'))
                answered = True
        else:
            raise AssertionError(f'Terminal timed out: {transcript!r}')
        waited, status = os.waitpid(pid, os.WNOHANG)
        # EOF on the controlling terminal precedes process reaping by a moment.
        while waited == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
            waited, status = os.waitpid(pid, os.WNOHANG)
        assert waited == pid, transcript
        reaped = True
        assert os.waitstatus_to_exitcode(status) == 1, transcript
        assert answered, transcript
        return transcript.decode('utf-8')
    finally:
        os.close(fd)
        if not reaped:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)


def source_namespace(source):
    namespace = {}
    exec(compile(source, '<edited source>', 'exec'), namespace)
    return namespace


def return_expression(source, function):
    tree = ast.parse(source)
    definition = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    return next(n.value for n in ast.walk(definition) if isinstance(n, ast.Return))


def annotation_is_unrestricted(annotation):
    """Recognize annotations that supply only unrestricted scalar information."""
    if annotation is typing.Any:
        return True
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is typing.Annotated:
        if not annotation_is_unrestricted(arguments[0]):
            return False
        import annotated_types
        from velnora.extensions import CustomCheck

        def restricts_values(metadata):
            if isinstance(metadata, annotated_types.GroupedMetadata):
                return any(restricts_values(member) for member in metadata)
            return isinstance(metadata, (
                annotated_types.Gt, annotated_types.Ge,
                annotated_types.Lt, annotated_types.Le,
                annotated_types.MultipleOf,
                annotated_types.MinLen, annotated_types.MaxLen,
                annotated_types.Timezone, annotated_types.Predicate,
                CustomCheck,
            ))

        return not any(restricts_values(metadata) for metadata in arguments[1:])
    if origin in (typing.Union, types.UnionType):
        return any(annotation_is_unrestricted(member) for member in arguments)
    return False


def annotation_accepts_scalar(annotation, value):
    """Check scalar membership independently using Python annotation semantics."""
    if annotation is typing.Any:
        return True
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(annotation_accepts_scalar(member, value) for member in arguments)
    if origin is typing.Literal:
        return any(type(value) is type(member) and value == member for member in arguments)
    if origin is typing.Annotated:
        return (annotation_accepts_scalar(arguments[0], value)
                and all(metadata_accepts_scalar(metadata, value)
                        for metadata in arguments[1:]))
    if annotation is None:
        return value is None
    if annotation is float:
        return isinstance(value, (int, float))
    if annotation is complex:
        return isinstance(value, (int, float, complex))
    return isinstance(value, annotation)


def metadata_accepts_scalar(metadata, value):
    """Evaluate standard value restrictions without the product's type checker."""
    try:
        return _metadata_accepts_scalar(metadata, value)
    except TypeError:
        # An inapplicable comparison or length restriction excludes this value.
        return False


def _metadata_accepts_scalar(metadata, value):
    import annotated_types
    import datetime

    if isinstance(metadata, annotated_types.GroupedMetadata):
        return all(metadata_accepts_scalar(member, value) for member in metadata)
    if isinstance(metadata, annotated_types.Gt):
        return value > metadata.gt
    if isinstance(metadata, annotated_types.Ge):
        return value >= metadata.ge
    if isinstance(metadata, annotated_types.Lt):
        return value < metadata.lt
    if isinstance(metadata, annotated_types.Le):
        return value <= metadata.le
    if isinstance(metadata, annotated_types.MultipleOf):
        return value % metadata.multiple_of == 0
    if isinstance(metadata, annotated_types.MinLen):
        return len(value) >= metadata.min_length
    if isinstance(metadata, annotated_types.MaxLen):
        return len(value) <= metadata.max_length
    if isinstance(metadata, annotated_types.Timezone):
        if not isinstance(value, datetime.datetime):
            return False
        if metadata.tz is None:
            return value.tzinfo is None
        if metadata.tz is ...:
            return value.tzinfo is not None
        return value.tzinfo == metadata.tz
    if isinstance(metadata, annotated_types.Predicate):
        return bool(metadata.func(value))
    return True
