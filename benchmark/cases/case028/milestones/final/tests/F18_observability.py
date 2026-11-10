# feature: F18
"""Acceptance through real program/test commands, signals, and a local proxy."""

import signal
import time

from _helpers import (Process, isolated_workspace, monotonic, read_bytes,
                      run_process, write_files)
from F10_helpers import f10_cli
from F12_helpers import F12Proxy, f12_downloaded
from F17_helpers import f17_run, f17_sources
from F18_helpers import (F18_SIGNAL_SOURCE, F18_TRACE_SOURCE, f18_assert_trace,
                         f18_state_location, f18_assert_module_stats,
                         f18_debug_snapshot, f18_phase_durations)


def test_source_trace_execution_order_depth_and_preserved_effects(f10_cli, f17_run):
    binary, built = f10_cli
    source = F18_TRACE_SOURCE + '''func main() {
    result := exercise()
    if err := os.WriteFile("result", []byte(fmt.Sprint(result)), 0600); err != nil { panic(err) }
    fmt.Println(result)
}
'''
    with isolated_workspace(base_env=built.env, overrides={"F18_BRANCH": "live"}) as work:
        write_files(work.cwd, {"trace.go": source})
        for flags in ([], ["-x"]):
            result = run_process([binary, "run", *flags, "trace.go"], cwd=work.cwd,
                                 env=work.env, timeout=30)
            assert result.returncode == 0, result
            assert result.stdout == b"17\n", result
            assert read_bytes(work.cwd / "result") == b"17", result
            (work.cwd / "result").unlink()
            if flags:
                f18_assert_trace(result.stderr, source, "trace.go")
            else:
                assert not any(line.startswith(b"+ ") for line in result.stderr.splitlines()), result

    test_source = F18_TRACE_SOURCE.replace("package main", "package suite", 1).replace(
        '"fmt"; "os"', '"fmt"; "os"; "testing"', 1) + '''func TestTrace(t *testing.T) {
    result := exercise()
    note(fmt.Sprint(result))
    if result != 17 { t.Fatal(result) }
}
'''
    for flags in (("-v",), ("-x", "-v")):
        # CLI options precede the target and native testing options. The
        # default target lets the existing helper preserve that ordering.
        observed = f17_run(f17_sources(test_source), flags, target=None,
                           environment={"F18_BRANCH": "live"})
        observed.passed(["TestTrace"])
        assert observed.effects == ["17"], observed
        if "-x" not in flags:
            assert not any(line.startswith(b"+ ") for line in observed.process.stderr.splitlines()), observed


def test_interrupt_reports_live_state_continues_and_resets_window(f10_cli):
    binary, built = f10_cli
    with isolated_workspace(base_env=built.env) as work:
        write_files(work.cwd, {"signal.go": F18_SIGNAL_SOURCE})
        with Process([binary, "run", "signal.go"], cwd=work.cwd, env=work.env, timeout=30) as process:
            process.read_until(b"phase-one-ready\n")
            process.send_signal(signal.SIGINT)
            offset = f18_state_location(process, 0, "phaseOne", F18_SIGNAL_SOURCE, "signal.go")
            # A new completed progress line after the report proves continued
            # execution, not merely that the process still exists.
            output_offset = len(process.snapshot().stdout)
            process.read_until(b"progress-one:", start=output_offset)
            time.sleep(1.25)
            write_files(work.cwd, {"advance": "next phase\n"})
            process.read_until(b"phase-two-ready\n", start=output_offset)
            second_sent = monotonic()
            process.send_signal(signal.SIGINT)
            f18_state_location(process, offset, "phaseTwo", F18_SIGNAL_SOURCE, "signal.go")
            output_offset = len(process.snapshot().stdout)
            process.read_until(b"progress-two:", start=output_offset)
            assert monotonic() - second_sent < 0.9, "Host scheduling did not leave a reliable sub-second interrupt window"
            process.send_signal(signal.SIGINT)
            result = process.finish(timeout=5)
            assert result.returncode == 130, result


def test_module_statistics_match_transfers_and_persistent_reuse(f10_cli, tmp_path):
    binary, built = f10_cli
    proxy = F12Proxy(tmp_path / "proxy")
    modules = [("stat.test/base", "v1.2.3"), ("stat.test/tree/math", "v1.4.2")]
    proxy.publish(*modules[0], {"base.go": "package base\nfunc Value() int { return 19 }\n"})
    proxy.publish(*modules[1], {"calc.go": 'package calc\nimport "stat.test/base"\n'
                  'func Compute() int { return base.Value()*2+3 }\n' + "// " + "padding " * 210 + "\n"})
    archive_bytes = sum((proxy.root / m / "@v" / (v + ".zip")).stat().st_size for m, v in modules)
    sources = {
        "run": ('package main\nimport ("fmt"; "stat.test/tree/math")\n'
                'func main() { fmt.Println(calc.Compute()) }\n'),
        "test": ('package suite\nimport ("fmt"; "testing"; "stat.test/tree/math")\n'
                 'func TestValue(t *testing.T) { v := calc.Compute(); fmt.Println(v); '
                 'if v != 41 { t.Fatal(v) } }\n'),
    }
    with proxy.serving():
        # Both public commands must wire the statistics. A cold/warm pair has
        # its own cache, so prior command coverage cannot seed the next pair.
        for command, source in sources.items():
            with isolated_workspace(base_env=built.env,
                                    overrides={"GOPROXY": proxy.url}) as work:
                work.env["ZELVIROCACHE"] = str(work.root / "archives")
                filename = "main.go" if command == "run" else "stats_test.go"
                write_files(work.cwd, {filename: source})
                args = ["run", "-stat", filename] if command == "run" else ["test", "-stat", "-v", "."]
                for warm in (False, True):
                    proxy.requests.clear()
                    work.env["GOPROXY"] = "off" if warm else proxy.url
                    result = run_process([binary, *args], cwd=work.cwd, env=work.env, timeout=45)
                    assert result.returncode == 0, result
                    assert b"41" in result.stdout.splitlines(), result
                    requests = list(proxy.requests)
                    if warm:
                        assert requests == [], requests
                    else:
                        for module, version in modules:
                            f12_downloaded(proxy, module, version)
                    f18_assert_module_stats(result, proxy, requests,
                                            hits=len(modules) if warm else 0,
                                            served=archive_bytes if warm else 0,
                                            stored=0 if warm else len(modules))

                # Downloads with persistence disabled must still be counted,
                # while neither existing archive reuse nor saves may be claimed.
                work.env.update(GOPROXY=proxy.url, ZELVIROCACHE="off")
                proxy.requests.clear()
                result = run_process([binary, *args], cwd=work.cwd, env=work.env, timeout=45)
                assert result.returncode == 0, result
                assert b"41" in result.stdout.splitlines(), result
                for module, version in modules:
                    f12_downloaded(proxy, module, version)
                f18_assert_module_stats(result, proxy, list(proxy.requests), hits=0, served=0, stored=0)


def test_debug_stops_inspect_live_values_and_resume(f10_cli):
    binary, built = f10_cli
    source = '''package main
func nested(argument int) int {
    local := argument*3+7
    trap()
    return local
}
func main() {
    value := 13
    trap()
    println(nested(value))
}
'''
    with isolated_workspace(base_env=built.env) as work:
        write_files(work.cwd, {"debug.go": source})
        with Process([binary, "run", "debug.go"], cwd=work.cwd, env=work.env, timeout=20) as process:
            depth, values, offset = f18_debug_snapshot(process, 0, "debug.go", 9)
            assert ("int", 13) in values, values
            process.send("unknown-command\n")
            response = process.read_until(b"debug> ", channel="stderr", start=offset)
            assert response.startswith(b"unknown command:"), response
            offset += len(response)
            # Inspecting again proves the unknown command did not resume.
            process.send("stack\n")
            response = process.read_until(b"debug> ", channel="stderr", start=offset)
            assert b"=== Call Stack ===" in response, response
            offset += len(response)
            process.send("cont\n")
            nested_depth, values, offset = f18_debug_snapshot(process, offset, "debug.go", 4)
            assert nested_depth > depth, (nested_depth, depth)
            assert ("int", 13) in values and ("int", 46) in values, values
            # EOF resumes the second stop and lets the computed result escape.
            result = process.finish()
            assert result.returncode == 0 and result.stdout == b"46\n", result


def test_elapsed_reports_bound_source_and_execution_waits(f10_cli, tmp_path):
    import http.server
    import threading

    binary, built = f10_cli
    # Two deliberately different phase allocations reject fixed reports and
    # swapped phases. Independent gates measure contained intervals, not a
    # hardware speed target or an inferred internal phase boundary.
    for trial, (command, source_wait, execution_wait) in enumerate((
            ("run", 0.8, 0.05), ("run", 0.05, 0.8),
            ("test", 0.8, 0.05), ("test", 0.05, 0.8))):
        proxy = F12Proxy(tmp_path / str(trial))
        proxy.publish("elapsed.test/value", "v1.0.0", {"value.go": "package value\nfunc Value() int { return 31 }\n"})
        waited = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = (proxy.root / self.path.lstrip("/")).resolve()
                if not path.is_relative_to(proxy.root) or not path.is_file():
                    self.send_error(404)
                    return
                if self.path.endswith(".zip"):
                    start = monotonic()
                    time.sleep(source_wait)
                    waited.append(monotonic() - start)
                content = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            def log_message(self, *args):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            with isolated_workspace(base_env=built.env, overrides={
                "GOPROXY": f"http://127.0.0.1:{server.server_port}", "ZELVIROCACHE": "off"}) as work:
                source = '''package main
import ("fmt"; "os"; "time"; "elapsed.test/value")
func main() {
 fmt.Println("execution-ready")
 for { if _, err := os.Stat("release"); err == nil { break }; time.Sleep(time.Millisecond) }
 fmt.Println(value.Value())
}
'''
                if command == "test":
                    source = source.replace("package main", "package suite").replace(
                        'import (', 'import ("testing"; ').replace(
                        "func main()", "func TestWait(t *testing.T)")
                filename = "timed.go" if command == "run" else "timed_test.go"
                write_files(work.cwd, {filename: source})
                args = ["run", "-stat", filename] if command == "run" else ["test", "-stat", "-v", "."]
                with Process([binary, *args], cwd=work.cwd, env=work.env, timeout=20) as process:
                    process.read_until(b"execution-ready\n")
                    start = monotonic()
                    time.sleep(execution_wait)
                    runtime_wait = monotonic() - start
                    write_files(work.cwd, {"release": "ready"})
                    result = process.finish()
                assert result.returncode == 0, result
                assert b"31" in result.stdout.splitlines(), result
                assert result.stdout.splitlines().count(b"execution-ready") == 1, result
                assert len(waited) == 1, waited
                reports = f18_phase_durations(result.stderr)
                # Printed nanoseconds can round by at most half a nanosecond.
                rounding = 0.5e-9
                assert waited[0] - rounding <= reports["compile"] <= result.elapsed - runtime_wait + rounding, (reports, waited, result)
                assert runtime_wait - rounding <= reports["execute"] <= result.elapsed - waited[0] + rounding, (reports, runtime_wait, result)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            assert not thread.is_alive(), "Timing proxy did not stop"
