# feature: F16
"""Observable REPL state, continuation, recovery, and input completion."""

from F16_helpers import f10_cli, f16_session


def test_successive_lines_retain_state_and_display_values(f16_session):
    with f16_session() as repl:
        # These declarations produce no value in a fresh session. Their later
        # use proves they executed, rather than merely producing no output.
        assert repl.line("type Counter struct { N int }") == b""
        assert repl.line('import text "strings"') == b""
        repl.statement("var item = Counter{N: 13}")
        repl.value("item.N", 13)
        repl.statement("item.N += 8")
        repl.value("item.N", 21)
        repl.statement("func scale(n int) int { return n * item.N }")
        repl.value("scale(3)", 63)
        repl.value('text.ToUpper("season")', "SEASON")
        repl.statement("item.N = scale(2)")
        repl.value("item.N", 42)
        repl.value("scale(2)", 84)
        # No-value suppression after globals exist is a known original bug,
        # not silently claimed by this fresh-session suppression check.
        repl.end()


def test_unfinished_constructs_continue_and_evaluate(f16_session):
    with f16_session() as repl:
        # Each fragment ends at a PRD-listed split position. Together these
        # cover parentheses, brackets, braces, operator, comma and semicolon.
        shown = []
        assert repl.line("(7 +", continuation=True) == b""
        shown.append(repl.value("8)*3", 45))
        assert repl.line("len([", continuation=True) == b""
        shown.append(repl.value("3]int{4, 5, 6})", 3))
        for fragment in ("[]int{", "2,"):
            assert repl.line(fragment, continuation=True) == b""
        shown.append(repl.value("5, 9}[1]", 5))
        for fragment in ("(func() int {", "var total = 1;", "total += 4;", "return total*6;"):
            assert repl.line(fragment, continuation=True) == b""
        shown.append(repl.value("})()", 30))
        # A complete line after the constructs is evaluated on its own.
        shown.append(repl.value("9*7-4", 59))
        assert shown == ["45", "3", "5", "30", "59"], shown
        result = repl.end()
        assert result.returncode == 0, result


def test_failed_submissions_are_reported_discarded_and_eof_ends(f16_session):
    with f16_session() as repl:
        repl.statement("var saved = 19")
        # A live session first proves values are displayed before failures.
        assert repl.value("saved+2", 21) == "21"
        failures = [repl.failure("missingCall()")]
        assert repl.value("saved", 19) == "19"
        assert repl.line("(", continuation=True) == b""
        failures.append(repl.failure("missingAgain())"))
        # The discarded "(" would make this line unbalanced if it were kept.
        assert repl.value("saved+3", 22) == "22"
        failures.append(repl.failure('panic("ordinary failure")'))
        assert repl.value("saved+4", 23) == "23"
        assert repl.line("if true {", continuation=True) == b""
        assert repl.line('panic("accumulated failure");', continuation=True) == b""
        failures.append(repl.failure("}"))
        assert repl.value("saved+5", 24) == "24"
        # EOF after a reported failure must terminate too, not await a repair.
        failures.append(repl.failure("lastMissingCall()"))
        assert len(failures) == 5 and all(f.startswith(b"Error:") for f in failures), failures
        result = repl.end()
        assert result.returncode == 0, result
    with f16_session() as repl:
        assert repl.value("6*8", 48) == "48"
        assert repl.line("(", continuation=True) == b""
        # Unfinished input does not prevent EOF from ending the session.
        result = repl.end()
        assert result.returncode == 0, result
