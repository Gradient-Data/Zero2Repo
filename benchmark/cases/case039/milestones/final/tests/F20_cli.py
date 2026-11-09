# feature: F20
"""Five planned CLI acceptance checks, using only public commands and results."""
from decimal import Decimal
from F08_snapshots import snapshot_ids
from F20_helpers import (cli_binary, cli_run, cli_ok, cli_json, cli_query, cli_rows,
                         cli_failure, cli_table, cli_terminal, cli_terminal_results)


def test_command_results_and_display_limit(cli_binary, tmp_path):
    cli_rows(cli_query(cli_binary, tmp_path, "memory://",
                       "SELECT 29 AS answer, TRUE AS ready, NULL AS absent, -3.125 AS fraction"),
             ["answer", "ready", "absent", "fraction"], [[29, True, None, Decimal("-3.125")]])
    dsn = "file://" + str(tmp_path / "display")
    cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e",
                    "CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)", dsn=dsn))
    expected = [[2, "elm"], [5, "birch"], [9, "oak"], [12, "ash"], [18, "pine"], [21, "fir"], [30, "yew"]]
    values = ",".join(f"({key},'{label}')" for key, label in expected)
    inserted = cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e",
                               "INSERT INTO items VALUES " + values, dsn=dsn))
    assert inserted == [{"rows_affected": len(expected)}]
    sql = "SELECT id,label FROM items ORDER BY id"
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id", "label"], expected)
    full = cli_table(cli_run(cli_binary, tmp_path, "-l", "0", "-e", sql, dsn=dsn), ["id", "label"])
    assert [[int(key), label] for key, label in full] == expected
    # The cap controls displayed record count, not which end supplies the rows.
    for limit in (3, 4, 10):
        limited = cli_table(cli_run(cli_binary, tmp_path, "-l", str(limit), "-e", sql, dsn=dsn), ["id", "label"])
        assert len(limited) == min(limit, len(full)), limited
        assert len({tuple(row) for row in limited}) == len(limited), limited
        assert all(row in full for row in limited), limited
        cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id", "label"], expected)
    written = cli_ok(cli_run(cli_binary, tmp_path, "-e",
        "UPDATE items SET label='cedar' WHERE id IN (2,9)", dsn=dsn, quiet=False))
    from F20_helpers import cli_affected
    assert cli_affected(written) == 2
    expected = [[key, "cedar" if key in (2,9) else label] for key,label in expected]
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id", "label"], expected)
    updated = cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e",
                              "UPDATE items SET label='willow' WHERE id IN (5,18)", dsn=dsn))
    assert updated == [{"rows_affected": 2}]
    deleted = cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e",
                              "DELETE FROM items WHERE id=12", dsn=dsn))
    assert deleted == [{"rows_affected": 1}]
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id", "label"],
             [[2,"cedar"],[5,"willow"],[9,"cedar"],[18,"willow"],[21,"fir"],[30,"yew"]])


def test_ordered_file_and_redirected_scripts(cli_binary, tmp_path):
    dsn = "file://" + str(tmp_path / "scripts")
    source = tmp_path / "commands.sql"
    source.write_text("""-- comment ; SELECT * FROM nonexistent;
CREATE TABLE script_rows (id INTEGER PRIMARY KEY, note TEXT, n INTEGER);
INSERT INTO script_rows VALUES (1,'left;right',4),(2,'it''s;quoted',9);
SELECT id,note,n FROM script_rows ORDER BY id;

UPDATE script_rows SET n=n+3 /* ; DELETE FROM script_rows; */ WHERE id=1;
SELECT id,note,n FROM script_rows ORDER BY id;
""", encoding="utf-8")
    records = cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-f", str(source), dsn=dsn))
    assert len(records) == 5, records
    assert "rows_affected" in records[0]
    assert records[1] == {"rows_affected": 2}
    cli_rows(records[2], ["id","note","n"], [[1,"left;right",4],[2,"it's;quoted",9]])
    assert records[3] == {"rows_affected": 1}
    cli_rows(records[4], ["id","note","n"], [[1,"left;right",7],[2,"it's;quoted",9]])
    records = cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", dsn=dsn, script="""
SELECT id,note,n FROM script_rows ORDER BY id;
INSERT INTO script_rows VALUES (3,'-- not a comment; /* text */',12); -- ; DELETE FROM script_rows;
UPDATE script_rows SET n=n*2 WHERE id=2;

DELETE FROM script_rows WHERE id=1;
SELECT id,note,n FROM script_rows ORDER BY id;
"""))
    assert len(records) == 5, records
    cli_rows(records[0], ["id","note","n"], [[1,"left;right",7],[2,"it's;quoted",9]])
    assert records[1:4] == [{"rows_affected": 1}] * 3
    expected = [[2,"it's;quoted",18],[3,"-- not a comment; /* text */",12]]
    cli_rows(records[4], ["id","note","n"], expected)
    cli_rows(cli_query(cli_binary, tmp_path, dsn, "SELECT id,note,n FROM script_rows ORDER BY id"),
             ["id","note","n"], expected)


def test_terminal_multiline_transactions_and_exit(cli_binary, tmp_path):
    dsn = "file://" + str(tmp_path / "terminal")
    cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", dsn=dsn, script="""
CREATE TABLE changes (id INTEGER PRIMARY KEY, n INTEGER);
INSERT INTO changes VALUES (1,10),(2,20),(3,30);
"""))
    records, errors, output = cli_terminal(cli_binary, tmp_path, dsn, """COMMIT
ROLLBACK
SELECT id,
n FROM changes
ORDER BY id;
BEGIN
BEGIN
UPDATE changes SET n=41 WHERE id=1;
DELETE FROM changes WHERE id=2;
INSERT INTO changes VALUES (4,44);
SELECT id,n FROM changes ORDER BY id;
COMMIT
SELECT id,n FROM changes ORDER BY id;
BEGIN
UPDATE changes SET n=81 WHERE id=1;
DELETE FROM changes WHERE id=3;
INSERT INTO changes VALUES (5,55);
SELECT id,n FROM changes ORDER BY id;
ROLLBACK
SELECT id,n FROM changes ORDER BY id;
BEGIN
UPDATE changes SET n=91 WHERE id=1;
DELETE FROM changes WHERE id=4;
INSERT INTO changes VALUES (6,66);
SELECT id,n FROM changes ORDER BY id;
exit
""")
    # Interactive errors are stderr Error: records, not process failure or prose.
    failures = [line for line in errors if line.startswith("Error:")]
    assert len(failures) == 3 and all(line[6:].strip() for line in failures), errors
    assert all(not line.strip() or line.startswith(("Error:", "Warning:")) for line in errors), errors
    records = cli_terminal_results(records, [
        "query", "control", "write", "write", "write", "query",
        "control", "query", "control", "write", "write", "write", "query",
        "control", "query", "control", "write", "write", "write", "query",
    ])
    committed = [[1,41],[3,30],[4,44]]
    for index, expected in [(0,[[1,10],[2,20],[3,30]]), (4,committed), (5,committed),
                            (9,[[1,81],[4,44],[5,55]]), (10,committed),
                            (14,[[1,91],[3,30],[6,66]])]:
        cli_rows(records[index], ["id","n"], expected)
    for index in (1,2,3,6,7,8,11,12,13):
        assert records[index] == {"rows_affected": 1}
    cli_rows(cli_query(cli_binary, tmp_path, dsn, "SELECT id,n FROM changes ORDER BY id"),
             ["id","n"], committed)
    # EOF is a second exit path with its own pending mutation, after the explicit
    # exit above has independently established rollback and usable persistence.
    records, errors, output = cli_terminal(cli_binary, tmp_path, dsn,
        "BEGIN\nUPDATE changes SET n=777 WHERE id=1;\nSELECT id,n FROM changes ORDER BY id;\n\x04")
    assert all(not line.strip() or line.startswith("Warning:") for line in errors), (errors, output)
    records = cli_terminal_results(records, ["control", "write", "query"])
    assert records[0] == {"rows_affected": 1}
    cli_rows(records[1], ["id","n"], [[1,777],[3,30],[4,44]])
    cli_rows(cli_query(cli_binary, tmp_path, dsn, "SELECT id,n FROM changes ORDER BY id"),
             ["id","n"], committed)


def test_cli_backup_and_latest_restore(cli_binary, tmp_path):
    # Read the documented backup identity, then observe selected and latest recovery.
    dsn = "file://" + str(tmp_path / "backups")
    cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", dsn=dsn, script="""
CREATE TABLE saved (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, n INTEGER CHECK(n>0));
INSERT INTO saved VALUES (1,'first',11),(2,'second',22);
"""))
    cli_ok(cli_run(cli_binary, tmp_path, "--snapshot", dsn=dsn))
    identities = snapshot_ids(tmp_path / "backups", "saved")
    assert len(identities) == 1
    older = next(iter(identities))

    cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", dsn=dsn, script="""
UPDATE saved SET n=37 WHERE id=1;
DELETE FROM saved WHERE id=2;
INSERT INTO saved VALUES (3,'third',33);
"""))
    expected = [[1,"first",37],[3,"third",33]]
    sql = "SELECT id,code,n FROM saved ORDER BY id,n"
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id","code","n"], expected)
    cli_ok(cli_run(cli_binary, tmp_path, "--snapshot", dsn=dsn))
    cli_json(cli_run(cli_binary, tmp_path, "-j", "-l", "0", dsn=dsn, script="""
DROP TABLE saved;
CREATE TABLE saved (id INTEGER, code TEXT, n INTEGER);
INSERT INTO saved VALUES (8,'current',88),(8,'current',0),(9,NULL,-3);
"""))
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id","code","n"],
             [[8,"current",0],[8,"current",88],[9,None,-3]])
    # Quiet successful backup/restore may print free text; success is exit status
    # plus independent reopened state, never the text itself.
    cli_ok(cli_run(cli_binary, tmp_path, "--restore", older, dsn=dsn))
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id","code","n"],
             [[1,"first",11],[2,"second",22]])
    restored = cli_run(cli_binary, tmp_path, "--restore", dsn=dsn)
    cli_ok(restored)
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id","code","n"], expected)
    for invalid in ("INSERT INTO saved VALUES (1,'new',10)",
                    "INSERT INTO saved VALUES (9,'first',10)",
                    "INSERT INTO saved VALUES (9,NULL,10)",
                    "INSERT INTO saved VALUES (9,'new',0)"):
        cli_failure(cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e", invalid, dsn=dsn))
    cli_rows(cli_query(cli_binary, tmp_path, dsn, sql), ["id","code","n"], expected)


def test_cli_failures_are_not_empty_success(cli_binary, tmp_path):
    cli_rows(cli_query(cli_binary, tmp_path, "memory://", "SELECT 17 AS n WHERE FALSE"), ["n"], [])
    invalid_db = cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e", "SELECT 17 AS n", dsn="unknown://invalid")
    cli_failure(invalid_db, "Error opening database:")
    missing_file = cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-f", str(tmp_path / "missing.sql"))
    cli_failure(missing_file)
    for sql in ("SELECT FROM", "SELECT * FROM absent_table"):
        failed = cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-e", sql)
        cli_failure(failed)
        assert failed.stdout == b"", failed.stdout
    # Script SQL errors are reported on stderr but the reference exits zero;
    # the one-command failure status must not be imposed on script execution.
    source = tmp_path / "failing.sql"
    source.write_text("SELECT * FROM absent_table;\n", encoding="utf-8")
    for result in (cli_run(cli_binary, tmp_path, "-j", "-l", "0", "-f", str(source)),
                   cli_run(cli_binary, tmp_path, "-j", "-l", "0", script=source.read_text(encoding="utf-8"))):
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert result.stderr.decode("utf-8").startswith("Error:"), result.stderr
        assert result.stdout == b"", result.stdout
    cli_rows(cli_query(cli_binary, tmp_path, "memory://", "SELECT 23 AS n"), ["n"], [[23]])
