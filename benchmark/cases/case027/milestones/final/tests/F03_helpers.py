# feature: F03
"""Helpers for the output-format suites.

Shell values of the printed forms (separators, placeholders, escape shape,
JSON message kinds) and readers for them.  No expected search result lives
here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from _helpers import HarnessError, ProductTimeout, RunResult, trisift_binary

__all__ = [
    "MATCH_SEP",
    "CONTEXT_SEP",
    "GROUP_SEP",
    "OMITTED_MATCH",
    "OMITTED_CONTEXT",
    "PREVIEW_MARKER",
    "SGR",
    "SGR_RESET",
    "strip_sgr",
    "has_sgr",
    "count_highlighted",
    "JSON_KINDS",
    "parse_json_stream",
    "without_timing",
    "FirstLine",
    "read_first_line_live",
]

#: Field separator of a matching line, of a context line, and the line
#: printed between non-contiguous context groups.
MATCH_SEP = ":"
CONTEXT_SEP = "-"
GROUP_SEP = "--"

#: Placeholders printed instead of an over-long line.
OMITTED_MATCH = "[Omitted long matching line]"
OMITTED_CONTEXT = "[Omitted long context line]"
#: Marker appended to the kept prefix of an over-long line in preview mode.
PREVIEW_MARKER = " [... omitted end of long line]"

#: Shape of one ANSI colour escape (Select Graphic Rendition) and the reset.
SGR = r"\x1b\[[0-9;]*m"
SGR_RESET = "\x1b[0m"
_SGR_RE = re.compile(SGR)


def strip_sgr(text: str) -> str:
    """Return ``text`` with every colour escape removed."""
    return _SGR_RE.sub("", text)


def has_sgr(text: str) -> bool:
    """Return whether ``text`` contains at least one colour escape."""
    return _SGR_RE.search(text) is not None


def _apply_sgr(state: dict, sequence: str) -> bool:
    """Apply semicolon SGR parameters; report a return to default rendition.

    Color payloads are consumed together: a zero RGB component or palette index
    is not a reset. Unknown parameters do not establish visible emphasis.
    """
    params = [int(p or "0") for p in sequence[2:-1].split(";")]
    enabled = {1: "bold", 2: "faint", 3: "italic", 4: "underline",
               5: "blink", 6: "blink", 7: "inverse", 8: "conceal",
               9: "strike", 20: "fraktur", 21: "underline",
               26: "proportional", 51: "frame", 52: "frame", 53: "overline",
               60: "ideogram", 61: "ideogram", 62: "ideogram",
               63: "ideogram", 64: "ideogram", 73: "script", 74: "script"}
    disabled = {10: ("font",), 22: ("bold", "faint"), 23: ("italic", "fraktur"),
                24: ("underline",), 25: ("blink",), 27: ("inverse",),
                28: ("conceal",), 29: ("strike",), 39: ("foreground",),
                49: ("background",), 50: ("proportional",), 54: ("frame",),
                55: ("overline",), 59: ("underline_color",), 65: ("ideogram",),
                75: ("script",)}
    reset = False
    i = 0
    while i < len(params):
        code = params[i]
        i += 1
        if code == 0:
            state.clear()
        elif code in enabled:
            state[enabled[code]] = code
        elif code in disabled:
            for attr in disabled[code]:
                state.pop(attr, None)
        elif 11 <= code <= 19:
            state["font"] = code
        elif 30 <= code <= 37 or 90 <= code <= 97:
            state["foreground"] = code
        elif 40 <= code <= 47 or 100 <= code <= 107:
            state["background"] = code
        elif code in (38, 48, 58):
            # Indexed and RGB colors, including padded decimal components.
            width = {5: 1, 2: 3}.get(params[i] if i < len(params) else None)
            if width is None or i + width >= len(params):
                break  # A malformed payload must not become independent styles.
            payload = params[i:i + width + 1]
            i += width + 1
            if all(0 <= v <= 255 for v in payload[1:]):
                attr = {38: "foreground", 48: "background", 58: "underline_color"}[code]
                state[attr] = tuple(payload)
        reset |= not state
    return reset


def count_highlighted(text: str, span: str) -> int:
    """Count exact wrapped spans displayed with effective visible SGR styling.

    Read the whole stream, not a suffix of an opening escape run. Opening
    controls must leave emphasis active while the text is emitted; a later
    reset cannot supply it. Each span still needs its own opening and closing
    controls, so coloring a whole surrounding line is not substring highlighting.
    Colors, padded decimals, multiple controls and equivalent resets are free.
    """
    assert span, "highlight observations need a nonempty span"
    state = {}
    end = 0
    count = 0
    for controls in re.finditer(rf"(?:{SGR})+", text):
        chunk = text[end:controls.start()]
        visible = bool(state.keys() - {"conceal", "underline_color"}) and "conceal" not in state
        candidate = end > 0 and chunk == span and visible
        reset = False
        for sgr in _SGR_RE.finditer(controls.group()):
            reset |= _apply_sgr(state, sgr.group())
        if candidate and reset:
            count += 1
        end = controls.end()
    return count


JSON_KINDS = ("begin", "match", "context", "end", "summary")


def parse_json_stream(result: RunResult) -> List[dict]:
    """Parse standard output as a JSON Lines message stream.

    Every line must be a JSON object with a ``type`` among
    :data:`JSON_KINDS` and a ``data`` object; anything else fails the test
    with the offending line.
    """
    text = result.out
    assert text == "" or text.endswith("\n"), f"stdout not newline-terminated\n{result.describe()}"
    messages = []
    for line in text.split("\n")[:-1]:
        try:
            msg = json.loads(line)
        except ValueError as exc:
            raise AssertionError(f"stdout line is not JSON: {line!r}\n{result.describe()}") from exc
        assert isinstance(msg, dict) and msg.get("type") in JSON_KINDS, f"unexpected message {line!r}"
        assert isinstance(msg.get("data"), dict), f"message without data object: {line!r}"
        messages.append(msg)
    return messages


def without_timing(messages: Sequence[dict]) -> List[dict]:
    """Return a deep copy of ``messages`` with the run-dependent fields removed.

    Removed: every ``elapsed`` / ``elapsed_total`` object and the
    ``bytes_printed`` statistic (it counts the printed timing text too).
    """
    return [project_json(m) for m in messages]


def project_json(msg, drop=()):
    kind, data = msg["type"], msg["data"]
    fields = {
        "begin": ("path",),
        "match": ("path", "lines", "line_number", "absolute_offset", "submatches"),
        "context": ("path", "lines", "line_number", "absolute_offset", "submatches"),
        "end": ("path", "binary_offset", "stats"),
        "summary": ("stats",),
    }
    def select(k, v):
        if k in ("path", "lines", "match"):
            return {"text": v["text"]}
        if k == "submatches":
            return [{"start": x["start"], "end": x["end"], "match": {"text": x["match"]["text"]}}
                    for x in v]
        if k == "stats":
            return {f: v[f] for f in ("searches", "searches_with_match", "matched_lines", "matches", "bytes_searched")
                    if f not in drop}
        return v
    return {"type": kind, "data": {k: select(k, data[k]) for k in fields[kind] if k not in drop}}


@dataclass
class FirstLine:
    """What a reader of the product's stdout pipe saw.

    ``line`` is the first line read (bytes, with its newline).  ``running``
    says whether the process was still running right after that line was
    read.  ``first_at`` and ``done_at`` are seconds from spawn to the first
    line and to process exit.  ``stdout`` is the complete output, ``code``
    the exit status, ``stderr`` the complete standard error.
    """

    line: bytes
    running: bool
    first_at: float
    done_at: float
    stdout: bytes
    stderr: bytes
    code: int


def read_first_line_live(args: Sequence[str], cwd, timeout: float = 300.0) -> FirstLine:
    """Run the product with stdout on a pipe and time its first output line.

    Reads one line from the pipe as soon as it is available, records whether
    the process is still running at that moment, then drains the rest.
    Raises :class:`ProductTimeout` when the run exceeds ``timeout`` and
    :class:`HarnessError` when the pipe closes without any line.
    """
    argv = [trisift_binary(), *args]
    start = time.monotonic()
    with open(os.devnull, "rb") as devnull:
        proc = subprocess.Popen(argv, cwd=os.fspath(cwd), stdin=devnull,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    err_chunks: List[bytes] = []
    err_thread = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    err_thread.start()
    timed_out = threading.Event()

    def kill():
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(timeout, kill)
    watchdog.start()
    try:
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = proc.stdout.read(1)
            if not chunk:
                break
            buf += chunk
        first_at = time.monotonic() - start
        running = proc.poll() is None
        rest = proc.stdout.read()
        code = proc.wait()
        done_at = time.monotonic() - start
    finally:
        watchdog.cancel()
    err_thread.join()
    stderr = b"".join(err_chunks)
    if timed_out.is_set():
        raise ProductTimeout(argv, timeout, buf + rest, stderr)
    if not buf.endswith(b"\n"):
        raise HarnessError(f"no complete line on stdout; exit={code} stdout={buf!r} stderr={stderr!r}")
    return FirstLine(buf, running, first_at, done_at, buf + rest, stderr, code)


def read_stdout_packets(args, cwd, timeout=60):
    """Observe stdout writes through a Linux packet-mode pipe, with bounded cleanup.

    Packet mode preserves write boundaries; it does not constrain computation,
    scheduling, or how many writes are used to deliver one output line.
    """
    import tempfile
    read_fd, write_fd = os.pipe2(os.O_DIRECT | os.O_CLOEXEC)
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen([trisift_binary(), *args], cwd=cwd,
                                stdin=subprocess.DEVNULL, stdout=write_fd, stderr=errors)
        os.close(write_fd)
        expired = threading.Event()
        def kill():
            expired.set()
            proc.kill()
        timer = threading.Timer(timeout, kill)
        timer.start()
        packets = []
        try:
            while True:
                packet = os.read(read_fd, 65536)
                if not packet:
                    break
                packets.append(packet)
                assert sum(map(len, packets)) < 1024 * 1024, "unbounded count output"
            code = proc.wait(timeout=timeout)
        finally:
            timer.cancel()
            os.close(read_fd)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        errors.seek(0)
        stderr = errors.read()
    assert not expired.is_set(), "count output did not finish within the bound"
    return packets, code, stderr


def read_before_later_file(args, cwd, later_file, prefix, timeout=10):
    """Require completed output on a pipe while a later content open is held.

    The lease establishes unfinished later input independently of CPU speed.
    The timeout is an execution watchdog, not a product throughput threshold.
    Always release the lease and reap the child, including assertion failures.
    """
    import select
    import tempfile
    from F00_observations import ReadGate
    from _helpers import wait_until

    argv = [trisift_binary(), *args]
    with ReadGate(later_file) as gate, tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=errors)
        try:
            wait_until(lambda: gate.requested or proc.poll() is not None, timeout=30,
                       message="later content open did not reach the gate")
            assert gate.requested, "search exited without reading the later matching file"
            observed = b""
            deadline = time.monotonic() + timeout
            while len(observed) < len(prefix):
                remaining = deadline - time.monotonic()
                assert remaining > 0, f"completed lines withheld behind later input: {observed!r}"
                ready, _, _ = select.select([proc.stdout], [], [], remaining)
                assert ready, f"completed lines withheld behind later input: {observed!r}"
                chunk = os.read(proc.stdout.fileno(), len(prefix) - len(observed))
                assert chunk, f"stdout closed before completed prefix: {observed!r}"
                observed += chunk
            assert observed == prefix
            gate.release()
            rest, _ = proc.communicate(timeout=30)
            errors.seek(0)
            return observed + rest, proc.returncode, errors.read()
        finally:
            gate.release()
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
