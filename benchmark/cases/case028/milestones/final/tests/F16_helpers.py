# feature: F16
"""Line-at-a-time CLI interaction using the shared bounded pipe driver."""

from contextlib import contextmanager
import re

import pytest

from _helpers import Process, isolated_workspace
from F10_helpers import f10_cli


class F16Session:
    def __init__(self, process):
        self.process = process
        initial = process.read_until(b"> ")
        assert initial == b"> ", process.snapshot()
        self.offset = len(initial)

    def line(self, source, *, continuation=False):
        assert "\n" not in source, "Send one input line per observation"
        self.process.send(source + "\n")
        frame = self.process.read_until(b"> ", start=self.offset)
        # A prompt begins a response or a new output line. A > followed by
        # space inside free diagnostic prose is not a prompt delimiter.
        while not (frame in (b"> ", b">> ") or
                   frame.endswith((b"\n> ", b"\n>> "))):
            frame += self.process.read_until(b"> ", start=self.offset + len(frame))
        self.offset += len(frame)
        if continuation:
            assert frame == b">> ", self.process.snapshot()
            return b""
        assert frame != b">> ", self.process.snapshot()
        return frame[:-2]

    def value(self, source, expected):
        body = self.line(source)
        match = re.fullmatch(rb": +([^\n]*)\n", body)
        assert match is not None, self.process.snapshot()
        assert match.group(1).decode() == str(expected), self.process.snapshot()
        return match.group(1).decode()

    def statement(self, source):
        body = self.line(source)
        # Statement effects are checked by later expressions. The original
        # can echo a stale global here: ledger F16.T01 records that defect.
        # Do not assert any particular stale value or require that echo.
        assert re.fullmatch(rb"(?:: +[^\n]*\n)?", body), self.process.snapshot()

    def failure(self, source):
        body = self.line(source)
        assert body.startswith(b"Error:"), self.process.snapshot()
        assert body[len(b"Error:"):].strip(), self.process.snapshot()
        return body

    def end(self):
        result = self.process.finish()
        assert result.returncode == 0, result
        return result


@pytest.fixture(scope="module")
def f16_session(f10_cli):
    binary, built = f10_cli

    @contextmanager
    def session():
        with isolated_workspace(base_env=built.env) as work:
            with Process([binary], cwd=work.cwd, env=work.env, timeout=45) as process:
                yield F16Session(process)

    return session
