# feature: F18
"""Read the CLI's labeled trace, state, and module-statistics records."""

from decimal import Decimal
import re


F18_TRACE_SOURCE = '''package main
import ("fmt"; "os")
func leaf(n int) int {
    value := n * 3
    return value
}
func outer(n int) int {
    answer := leaf(n + 1)
    return answer + 2
}
func exercise() int {
    seed := 4
    if os.Getenv("F18_BRANCH") == "never" {
        seed = 1000
    }
    result := outer(seed)
    for again := 0; again < 2; again++ {
        result += leaf(again) - 3*again
    }
    return result
}
'''


F18_SIGNAL_SOURCE = '''package main
import ("fmt"; "os"; "time")
func phaseOne() {
    fmt.Println("phase-one-ready")
    for i := 0; ; i++ {
        fmt.Printf("progress-one:%d\\n", i)
        time.Sleep(10 * time.Millisecond)
        if _, err := os.Stat("advance"); err == nil { return }
    }
}
func phaseTwo() {
    fmt.Println("phase-two-ready")
    for i := 0; ; i++ {
        fmt.Printf("progress-two:%d\\n", i)
        time.Sleep(10 * time.Millisecond)
    }
}
func main() {
    phaseOne()
    phaseTwo()
}
'''


def f18_trace_records(stderr):
    records = []
    for line in stderr.decode().splitlines():
        if not line.startswith("+ "):
            continue
        match = re.fullmatch(r"\+ ( *)(.+?):([0-9]+): (.*)", line)
        assert match is not None, line
        indent, source, number, text = match.groups()
        records.append((len(indent), source, int(number), text))
    return records


def f18_assert_trace(stderr, source, filename):
    records = f18_trace_records(stderr)
    # Only the caller's source is inspected; generated test-driver code and
    # library tracing are not specified by this feature.
    own = [r for r in records if r[1] == filename]
    assert own, (filename, records)
    lines = source.splitlines()
    for _, _, number, text in own:
        assert 1 <= number <= len(lines), (number, lines)
        assert text.strip() == lines[number - 1].strip(), (number, text, lines[number - 1])
    dead = lines.index("        seed = 1000") + 1
    assert all(r[2] != dead for r in own), own

    # Ordered subsequence permits repeated line records and extra legitimate
    # records, without permitting a source scan to impersonate execution.
    steps = ["    seed := 4", "    result := outer(seed)",
             "    answer := leaf(n + 1)", "    value := n * 3",
             "    return value", "    return answer + 2", "    return result"]
    cursor, depths = 0, []
    for statement in steps:
        number = lines.index(statement) + 1
        found = next((i for i in range(cursor, len(own)) if own[i][2] == number), None)
        assert found is not None, (statement, own)
        depths.append(own[found][0])
        cursor = found + 1
    assert depths[0] == depths[1] == depths[6], depths
    assert depths[2] == depths[5] > depths[1], depths
    assert depths[3] == depths[4] > depths[2], depths
    # leaf runs three times; a trace in execution order shows each execution.
    body = lines.index("    value := n * 3") + 1
    assert sum(1 for r in own if r[2] == body) >= 3, own


def f18_state_location(process, start, function, source, filename):
    header = process.read_until(b"=== zelviro execution state (", channel="stderr", start=start)
    end_header = process.read_until(b"\n", channel="stderr", start=start + len(header))
    # The header's machine address is deliberately opaque, never an oracle.
    offset = start + len(header) + len(end_header)
    at = process.read_until(b"\n", channel="stderr", start=offset)
    match = re.fullmatch(rb"  at ([^\s]+) \(([^\n]+):([0-9]+):([0-9]+)\)\n", at)
    assert match is not None, process.snapshot()
    name, path, number, column = match.groups()
    # Package qualification does not change the source function's identity.
    assert name.decode().rsplit(".", 1)[-1] == function, process.snapshot()
    assert path.decode() == filename, process.snapshot()
    lines = source.splitlines()
    first = lines.index(f"func {function}() {{") + 1
    last = next(i + 1 for i in range(first, len(lines)) if lines[i] == "}")
    assert first <= int(number) <= last, (at, first, last)
    assert 1 <= int(column) <= len(lines[int(number) - 1]) + 1, at
    return offset + len(at)


def f18_module_stats(stderr):
    text = stderr.decode()
    network = re.findall(r"^\s*network: +([0-9]+) requests, ([0-9.]+) (B|KiB|MiB|GiB) in ([^\n]+)$", text, re.M)
    cache = re.findall(r"^\s*cache: +([0-9]+) hits(?: \([0-9]+ via go cache\))?, ([0-9.]+) (B|KiB|MiB|GiB) served, ([0-9]+) stored$", text, re.M)
    assert len(network) == len(cache) == 1, text
    requests, received, receive_unit, _elapsed = network[0]
    hits, served, serve_unit, stored = cache[0]
    return {"requests": int(requests), "received": (received, receive_unit),
            "hits": int(hits), "served": (served, serve_unit), "stored": int(stored)}


def f18_bytes_equal(display, actual):
    number, unit = display
    scale = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}[unit]
    if unit == "B":
        assert re.fullmatch(r"[0-9]+", number), display
        assert int(number) == actual, (display, actual)
    else:
        assert re.fullmatch(r"[0-9]+\.[0-9]{2}", number), display
        # Accept the full rounding interval, including either tie direction.
        assert abs(Decimal(number) * scale - actual) <= Decimal("0.005") * scale, (display, actual)


def f18_assert_module_stats(result, proxy, requests, *, hits, served, stored):
    stats = f18_module_stats(result.stderr)
    assert stats["requests"] == len(requests), (stats, requests)
    transferred = sum((proxy.root / r["path"].lstrip("/")).stat().st_size
                      for r in requests if r["status"] == 200)
    f18_bytes_equal(stats["received"], transferred)
    assert stats["hits"] == hits, stats
    f18_bytes_equal(stats["served"], served)
    assert stats["stored"] == stored, stats


def f18_debug_snapshot(process, offset, filename, line):
    body = process.read_until(b"debug> ", channel="stderr", start=offset)
    stop = re.search(rb"trap at ip=[^\n]+ \(([^\n]+):([0-9]+):([0-9]+)\)\n", body)
    assert stop is not None, body
    assert stop.group(1).decode() == filename and int(stop.group(2)) == line, body
    offset += len(body)
    process.send("stack\n")
    body = process.read_until(b"debug> ", channel="stderr", start=offset)
    assert b"=== Call Stack ===\n" in body, body
    frames = list(re.finditer(rb"^--- Frame [^\n]+ ---\n", body, re.M))
    assert frames, body
    # Frame metadata and row roles are opaque; the baseline does not reliably
    # associate values with parameter positions or variable names.
    end = frames[1].start() if len(frames) > 1 else len(body)
    globals_header = re.search(rb"^--- Globals ---$", body, re.M)
    if globals_header is not None:
        end = min(end, globals_header.start())
    first = body[frames[0].end():end]
    values = []
    for row in first.splitlines():
        match = re.fullmatch(rb"  mem\[ *[0-9]+ *\] +\S+(?: \S+)* {2,}int {2,}([+-]?[0-9]+)(?: +.*)?", row)
        if match:
            values.append(("int", int(match.group(1))))
    return len(frames), values, offset + len(body)


def f18_phase_durations(stderr):
    # Go duration syntax, including compound units, is a public printed form.
    units = {"ns": Decimal("1e-9"), "us": Decimal("1e-6"), "µs": Decimal("1e-6"),
             "ms": Decimal("1e-3"), "s": Decimal(1), "m": Decimal(60), "h": Decimal(3600)}
    result = {}
    for label in ("compile", "execute"):
        rows = re.findall(r"^\s*" + label + r": +([^\n]+)$", stderr.decode(), re.M)
        assert len(rows) == 1, stderr
        parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ns|us|µs|ms|s|m|h)", rows[0])
        assert parts and "".join(n+u for n,u in parts) == rows[0], rows
        result[label] = float(sum(Decimal(n)*units[u] for n,u in parts))
    return result
