# feature: F17
"""Run real package suites and decode their public Go testing records."""

from collections import Counter
from dataclasses import dataclass

import pytest

from _helpers import (Process, isolated_workspace, monotonic, parse_json_lines,
                      read_bytes, run_process, write_files)
from F10_helpers import f10_cli
from F12_helpers import F12Proxy


F17_SUPPORT = '''package suite
import ("fmt"; "os")
func note(value string) {
    f, err := os.OpenFile(os.Getenv("F17_RECORD"), os.O_APPEND|os.O_WRONLY, 0600)
    if err != nil { panic(err) }
    if _, err := fmt.Fprintln(f, value); err != nil { panic(err) }
    if err := f.Close(); err != nil { panic(err) }
}
'''


@dataclass
class F17Suite:
    process: object
    events: list
    effects: list
    suite_elapsed: object

    def cases(self, action):
        return [e["Test"] for e in self.events if e.get("Action") == action and "Test" in e]

    def passed(self, names):
        assert self.process.returncode == 0, self.process
        assert Counter(self.cases("pass")) == Counter(names), (self.events, self.process)


@pytest.fixture(scope="module")
def f17_run(f10_cli):
    binary, built = f10_cli

    def run(files, flags=("-v",), *, target=".", proxy="off", timeout=60,
            start_marker=None, release_after=None, environment=None):
        with isolated_workspace(base_env=built.env,
                                overrides={"GOPROXY": proxy, "ZELVIROCACHE": "off",
                                           **(environment or {})}) as work:
            write_files(work.cwd, files)
            record = write_files(work.root, {"effects": b""})["effects"]
            work.env["F17_RECORD"] = str(record)
            argv = [binary, "test"]
            if target is not None:
                argv.append(target)
            argv.extend(flags)
            elapsed = None
            with Process(argv, cwd=work.cwd, env=work.env, timeout=timeout) as process:
                process.eof()
                if start_marker is not None:
                    process.read_until(start_marker)
                    started = monotonic()
                if release_after is not None:
                    channel, marker, filename = release_after
                    process.read_until(marker, channel=channel)
                    write_files(work.cwd, {filename: b"continue\n"})
                result = process.finish()
                if start_marker is not None:
                    elapsed = monotonic() - started
            converted = run_process(["go", "tool", "test2json", "-p", "suite"],
                                    cwd=work.cwd, env=work.env,
                                    input=result.stdout, timeout=30)
            assert converted.returncode == 0, converted
            events = parse_json_lines(converted.stdout)
            return F17Suite(result, events, read_bytes(record).decode().splitlines(), elapsed)

    return run


def f17_sources(source, **extra):
    return {"support_test.go": F17_SUPPORT, "cases_test.go": source, **extra}
