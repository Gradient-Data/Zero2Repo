# feature: F20
"""CLI transport and explicit public result forms; no private database files."""
import os
from decimal import Decimal
from json import JSONDecodeError
from pathlib import Path
import pty
import re
import subprocess
import termios

import pytest
from F01_helpers import product_root
from _helpers import locate_artifact, run_command, parse_json, parse_json_lines, make_environment


@pytest.fixture(scope="session")
def cli_binary():
    """Use the CLI supplied by the environment's required product build.

    Tests may run without write permission to the product or its build tree.
    Missing or non-executable artifacts fail; no rebuild or alternate binary is
    selected. CARGO_TARGET_DIR retains its standard explicit target location.
    """
    root = product_root()
    target = Path(os.environ.get("CARGO_TARGET_DIR", str(root / "target")))
    return locate_artifact(target / "release/velnora", root=root, executable=True)


def cli_run(binary, directory, *args, dsn="memory://", script="", quiet=True):
    return run_command([binary, *(["-q"] if quiet else []), "-d", dsn, *args], cwd=directory,
                       timeout=30, input_bytes=script.encode("utf-8"))


def cli_ok(result):
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert not result.stderr, (result.stdout, result.stderr)
    return result


def cli_json(result):
    cli_ok(result)
    return parse_json_lines(result.stdout)


def cli_query(binary, directory, dsn, sql):
    records = cli_json(cli_run(binary, directory, "-j", "-l", "0", "-e", sql, dsn=dsn))
    assert len(records) == 1, records
    return records[0]


def json_value_equal(actual, expected):
    """Compare JSON values exactly, independent of a number's decimal lexeme.

    JSON has one number type. Decimal preserves exponent-form integers across
    the entire i64 domain; bool remains a separate JSON type despite Python's
    bool/int inheritance. No binary float conversion or tolerance is used.
    """
    if type(actual) in (int, Decimal) and type(expected) in (int, Decimal):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            json_value_equal(a, e) for a, e in zip(actual, expected))
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            json_value_equal(actual[k], expected[k]) for k in actual)
    return actual == expected


def cli_rows(record, columns, rows):
    assert record["columns"] == columns, record
    assert json_value_equal(record["rows"], rows), record
    assert record["count"] == len(rows), record


def cli_terminal_results(records, sequence):
    """Match required results, allowing a zero-row control acknowledgement.

    Each control position belongs to a successful transaction command in the
    submitted script. Only that position can consume an optional zero-row
    record; failed commands and ordinary queries/writes get no such allowance.
    Return the required query/write records without changing their contents.
    """
    position = 0
    results = []
    for kind in sequence:
        if kind == "control":
            if position < len(records) and json_value_equal(
                    records[position], {"rows_affected": 0}):
                position += 1
            continue
        assert kind in ("query", "write"), kind
        assert position < len(records), (sequence, records)
        record = records[position]
        fields = {"columns", "rows", "count"} if kind == "query" else {"rows_affected"}
        if kind == "query":
            # Query objects declare required fields; only mutation objects have
            # an exact shape in the public CLI contract.
            assert fields <= set(record), (kind, position, record)
        else:
            assert set(record) == fields, (kind, position, record)
        results.append(record)
        position += 1
    assert position == len(records), (sequence, records[position:])
    return results


def cli_failure(result, prefix="Error:"):
    assert result.returncode == 1, (result.stdout, result.stderr)
    lines = result.stderr.decode("utf-8").splitlines()
    assert any(line.startswith(prefix) and line[len(prefix):].strip() for line in lines), lines


def cli_table(result, columns):
    """Read pipe-delimited header/data records, ignoring free decoration lines.

    This observer uses projections with multiple columns and cells without pipes
    or newlines. Separators and truncation prose are not data records and carry
    no pipe-delimited fields. It never extracts numbers from those decorations.
    """
    cli_ok(result)
    records = [line.split(" | ") for line in result.stdout.decode("utf-8").splitlines()
               if " | " in line]
    assert records and records[0] == columns, result.stdout
    assert all(len(row) == len(columns) for row in records), result.stdout
    return records[1:]


def cli_terminal(binary, directory, dsn, commands):
    """Give the actual CLI a terminal stdin, with separate captured output streams.

    Stdout is redirected to avoid terminal input echo and cursor redraws.
    Prompts may prefix a JSON record; their prose is not read or asserted. A bounded
    command script includes its own interactive exit. Child failures propagate.
    """
    master, slave = pty.openpty()
    process = None
    try:
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        assert os.isatty(slave)
        process = subprocess.Popen(
            [binary, "-q", "-j", "-l", "0", "-d", dsn], cwd=directory,
            stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=make_environment({"TERM": "dumb", "HOME": str(directory)}))
        os.close(slave)
        slave = None
        payload = commands.encode("utf-8")
        # Keep the canonical terminal queue bounded; inputs here fit in one write.
        assert len(payload) < 4096
        assert os.write(master, payload) == len(payload)
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
        # Each result is a complete JSON object at the end of a stdout line.
        # Prompt text may itself contain braces: only a fully parsed JSON suffix
        # is a record. Rejected candidate starts are prompt syntax, not product
        # failures. The caller checks every expected result and stderr error.
        records = []
        for line in stdout.splitlines():
            candidates = []
            for offset, byte in enumerate(line):
                if byte != ord("{"):
                    continue
                try:
                    candidate = parse_json(line[offset:])
                except JSONDecodeError:
                    continue
                if (isinstance(candidate, dict) and
                        ("rows_affected" in candidate or
                         {"columns", "rows", "count"} <= candidate.keys())):
                    candidates.append(candidate)
            assert len(candidates) <= 1, (line, candidates)
            records.extend(candidates)
        assert records, (stdout, stderr)
        errors = re.sub(rb"\x1b\[[0-9;]*m", b"", stderr).decode("utf-8").splitlines()
        return records, errors, stdout
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        if slave is not None:
            os.close(slave)
        os.close(master)


def cli_affected(result, check_stderr=True):
    """Read the affected-row line from stdout.

    Without -q the documents leave the connection message's stream open, so a
    non-quiet run is only required to succeed, not to keep standard error empty.
    """
    assert result.returncode == 0, (result.stdout, result.stderr)
    if check_stderr:
        assert not result.stderr, (result.stdout, result.stderr)
    lines = result.stdout.decode("utf-8").splitlines()
    counts = [int(match[1]) for line in lines
              if (match := re.fullmatch(r"([+-]?[0-9]+) rows affected", line))]
    assert len(counts) == 1, result.stdout
    return counts[0]
