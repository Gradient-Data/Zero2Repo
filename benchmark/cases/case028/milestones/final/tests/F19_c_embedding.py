# feature: F19
"""C embedding acceptance tests; expected results observed on the baseline."""

from F19_helpers import f19_c_driver, f19_c_result


def test_c_labeled_evaluation_retains_state(f19_c_driver):
    # F19.T01: actual computed values, including calls to retained declarations.
    records, _ = f19_c_driver([
        ("arithmetic.go", "7 * 11 - 6"),
        ("text.go", '"harbor" + "light"'),
        ("declare.go", "var balance = 14\n"
         "func adjust(delta int) int { balance += delta; return balance }"),
        ("add.go", "adjust(9)"),
        ("subtract.go", "adjust(-4)"),
        ("read.go", "balance"),
        ("text-again.go", '"ridge" + "way"'),
        ("read-again.go", "balance * 2"),
    ])
    for record in records:
        assert record["status"] == 0, record
        assert record["error"] is None, record
    # Declaration results are deliberately not pinned: retained state is read
    # through later expressions instead of assuming declarations have no value.
    for index, expected in [(0, "71"), (1, "harborlight"), (3, "23"),
                            (4, "19"), (5, "19"), (6, "ridgeway"), (7, "38")]:
        f19_c_result(records[index], expected)


def test_c_empty_result_error_and_host_continuation(f19_c_driver):
    # F19.T02: all observations belong to one live host/interpreter. The host
    # frees every returned string and the handle using the public C operations.
    records, _ = f19_c_driver([
        ("live.go", "23 + 8"),
        ("empty.go", "// no value\n"),
        ("setup.go", "var total = 5\nfunc advance() { total += 12 }"),
        ("advance.go", "advance()"),
        ("before-error.go", "total"),
        ("rejected.go", "missingFunction()"),
        ("after-error.go", "total + 4"),
        ("continue.go", "advance()"),
        ("continued.go", "total"),
    ])
    for index in (0, 1, 2, 3, 4, 6, 7, 8):
        assert records[index]["status"] == 0, records[index]
        assert records[index]["error"] is None, records[index]
    for index, expected in [(0, "31"), (1, ""), (4, "17"),
                            (6, "21"), (8, "29")]:
        f19_c_result(records[index], expected)
    failure = records[5]
    assert failure["status"] == -1, failure
    assert failure["result"] is None, failure
    assert isinstance(failure["error"], str) and failure["error"], failure
    # Error prose is not a contract; the separate error parameter and status
    # are. Subsequent exact results above prove the host continued real work.
