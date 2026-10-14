"""Mock tests for the post-trial transcript scan (no model calls, no docker).

Fixtures under ``fixtures/`` are small recorded-shape transcripts for a
fictional case whose banned names come from ``fixtures/case_widget/source``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cbrun import transcript_scan as ts
from cbrun.results import TrialResult, format_reward_matrix, write_summary

FIXTURES = Path(__file__).parent / "fixtures"
CASE = FIXTURES / "case_widget"


@pytest.fixture(scope="module")
def rules() -> ts.ScanRules:
    return ts.load_rules(CASE)


def _scan(name: str) -> dict:
    return ts.scan_trial(FIXTURES / name, CASE)


def _rules_by_line(report: dict) -> dict[int, tuple[str, str]]:
    return {h["line"]: (h["rule"], h["severity"]) for h in report["hits"]}


# --------------------------------------------------------------------------- rules


def test_rules_come_from_denylist_and_manifest(rules):
    assert "widgetlib" in rules.names
    assert "python-widgetlib" in rules.names
    assert "acme/widgetlib" in rules.slugs
    assert "github.com/acme/widgetlib" in rules.slugs
    # Sensitive terms the public Contract discloses are no evidence of access.
    assert "cmd/gizmo" in rules.disclosed_terms
    assert "gizmo-cli" in rules.disclosed_terms
    assert "gizmo-cli" not in rules.names
    # Words that only appear apart in the public text do not disclose a compound.
    assert "widget-core" not in rules.disclosed_terms
    assert "widget-core" in rules.names
    # A file named after the product under a generic directory still counts
    # when the product name itself is not public.
    assert "src/widgetlib.py" not in rules.disclosed_terms
    # Prose terms only feed mentions.
    assert "Jane Doe" in rules.mention_terms


@pytest.mark.parametrize(
    "term,disclosed",
    [
        ("gizmo-cli", True),
        ("Gizmo CLI", True),
        ("cmd/gizmo", True),
        ("github.com/acme/gizmo", False),  # "acme" is not public
        ("widget-core", False),  # "widget" and "core" only apart
        ("objects-store", False),  # "objects/store" is a path, not the phrase
        ("objects/store", True),
    ],
)
def test_disclosure_needs_the_phrase(term, disclosed):
    public = ts._public_text(CASE) + " under . git / objects / store "
    assert ts._is_disclosed(term, public) is disclosed


@pytest.mark.parametrize(
    "candidate,expected",
    [
        ("widgetlib", "widgetlib"),
        ("widgetlib-2.0.1.tar.gz", "widgetlib"),
        ("widgetlib-2.0.1-py3-none-any.whl", "widgetlib"),
        ("widgetlib==2.0.1", "widgetlib"),
        ("WidgetLib[extra]", "widgetlib"),
        ("widgetlib@1.2.0", "widgetlib"),
        ("*widgetlib*", "widgetlib"),
        ("widgetlib_helpers", None),
        ("mywidgetlib", None),
        ("requests", None),
    ],
)
def test_name_matching_is_whole_component(rules, candidate, expected):
    assert ts.match_name(candidate, rules) == expected


def test_slug_matching_needs_boundaries(rules):
    assert ts.match_slug("https://github.com/acme/widgetlib.git", rules)
    assert ts.match_slug("acme/widgetlib-extras", rules) is None
    assert ts.match_slug("notacme/widgetlib", rules) is None


def test_host_classes():
    assert ts.is_code_host("github.com")
    assert ts.is_code_host("gitlab.com")
    assert ts.is_code_host("gitlab.gnome.org")
    assert ts.is_code_host("ghproxy.net")
    assert ts.is_code_host("cdn.jsdelivr.net", "/gh/acme/widgetlib/x.py")
    assert not ts.is_code_host("cdn.jsdelivr.net", "/npm/left-pad")
    assert not ts.is_code_host("pypi.org")
    assert ts.is_registry_host("files.pythonhosted.org")
    assert ts.is_registry_host("mirrors.aliyun.com")
    assert ts.is_registry_host("registry.npmjs.org")
    assert not ts.is_registry_host("www.example.gov")


# --------------------------------------------------------------------------- shell parsing


def test_heredoc_body_written_to_file_is_dropped():
    cmd = "cat > a.py <<'EOF'\nimport urllib; urllib.urlopen('https://github.com/x/y')\nEOF\necho done"
    stripped, scripts = ts.split_heredocs(cmd)
    assert "github" not in stripped
    assert scripts == []


def test_heredoc_body_fed_to_interpreter_is_kept():
    cmd = "cd /tmp && python3 - <<'EOF'\nprint(1)\nEOF"
    _, scripts = ts.split_heredocs(cmd)
    assert scripts == ["print(1)"]


@pytest.mark.parametrize(
    "command,rule,severity",
    [
        ("git clone https://github.com/acme/widgetlib", "code_host_fetch", "high"),
        ("git clone git@github.com:acme/widgetlib.git", "code_host_fetch", "high"),
        ("curl -L https://gitee.com/other/thing/archive/main.zip -o t.zip", "code_host_fetch", "medium"),
        ("wget https://codeload.github.com/acme/widgetlib/tar.gz/main", "code_host_fetch", "high"),
        ("pip install git+https://github.com/acme/widgetlib", "code_host_fetch", "high"),
        ("npm install github:someone/thing", "code_host_fetch", "medium"),
        ("pip install widgetlib", "banned_name_fetch", "high"),
        ("sudo -E pip3 install -U widgetlib==2.0", "banned_name_fetch", "high"),
        ("npx widgetlib --help", "banned_name_fetch", "high"),
        ("pip download requests", "registry_source_download", "medium"),
        ("npm pack widgetlib", "registry_source_download", "high"),
        ("go mod download example.com/acme/widgetlib", "registry_source_download", "high"),
        ("apt-get source python-widgetlib", "registry_source_download", "high"),
        ("curl -O https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz", "registry_source_download", "medium"),
        ("pip show widgetlib", "banned_name_lookup", "medium"),
        ("python3 -c 'import widgetlib'", "banned_name_lookup", "medium"),
        ("node -e \"require('widgetlib')\"", "banned_name_lookup", "medium"),
        ("ls /usr/lib/python3/dist-packages/widgetlib", "banned_name_lookup", "medium"),
        ("find / -type d \\( -name widgetlib -o -name foo \\)", "banned_name_lookup", "medium"),
        ("curl https://widgetlib.readthedocs.io/en/latest/", "banned_name_fetch", "high"),
    ],
)
def test_shell_rules(rules, command, rule, severity):
    findings, _ = ts._Analyzer(rules).shell(command)
    assert (rule, severity) in {(f.rule, f.severity) for f in findings}, findings


@pytest.mark.parametrize(
    "command",
    [
        "pip install requests pytest",
        "pip install -r requirements.txt -e .",
        "npm install && npm pack",
        "npm install @types/node typescript",
        "go mod download",
        "go get github.com/spf13/cobra@v1.8.0",
        "curl -sI https://registry.npmjs.org/left-pad",
        "curl -sSL -o /tmp/d.zip https://www.example.gov/data/model.zip",
        "ls /app/widgetlib && cat widgetlib/core.py",
        "echo https://github.com/acme/widgetlib",
        "cat > notes.md <<'EOF'\ngit clone https://github.com/acme/widgetlib\nEOF",
        "python3 -c 'import json, os'",
    ],
)
def test_ordinary_commands_are_not_flagged(rules, command):
    findings, _ = ts._Analyzer(rules).shell(command)
    assert not [f for f in findings if f.severity in ts.REVIEW_SEVERITIES], findings


# --------------------------------------------------------------------------- whole trials


def test_clean_trial_records_only_mentions():
    report = _scan("trial_clean")
    assert report["verdict"] == "clean"
    assert report["needs_review"] is False
    assert report["counts"]["high"] == report["counts"]["medium"] == 0
    # The web search names the product: recorded as a low mention.
    mentions = [h for h in report["hits"] if h["rule"] == "mention"]
    assert mentions and all(not h["needs_review"] for h in mentions)
    assert any("WebSearch" == h["tool"] for h in mentions)


def test_leaky_trial_flags_each_attempt_with_evidence():
    report = _scan("trial_leaky")
    assert report["verdict"] == "needs_review" and report["needs_review"] is True
    by_line = _rules_by_line(report)
    assert by_line[1] == ("code_host_fetch", "high")  # git clone
    assert by_line[3] == ("registry_source_download", "high")  # curl sdist
    assert by_line[5] == ("registry_source_download", "high")  # pip download
    assert by_line[7] == ("code_host_fetch", "medium")  # WebFetch gitlab
    assert by_line[9] == ("registry_source_download", "medium")  # unrelated sdist
    assert by_line[11] == ("code_host_fetch", "high")  # urllib in heredoc
    assert by_line[13] == ("banned_name_lookup", "medium")  # pip show
    assert by_line[15] == ("banned_name_lookup", "medium")  # Read site-packages
    assert by_line[17] == ("banned_name_lookup", "medium")  # find -name
    assert by_line[19] == ("banned_name_in_output", "medium")  # make printed a download
    assert by_line[21] == ("code_host_fetch", "medium")  # ghproxy mirror
    clone = next(h for h in report["hits"] if h["line"] == 1)
    assert clone["file"] == "container_logs/usage/0/-app/session.jsonl"
    assert "git clone" in clone["snippet"]
    assert clone["network_failure"] is True
    assert "Failed to connect" in clone["result_excerpt"]
    # One hit per attempt: the clone's "Cloning into" output is not a second hit.
    assert sum(1 for h in report["hits"] if h["line"] == 1) == 1


def test_other_backend_shapes():
    report = _scan("trial_codex")
    by_line = _rules_by_line(report)
    assert by_line[1] == ("code_host_fetch", "high")  # function_call argv
    assert by_line[3] == ("banned_name_lookup", "medium")  # command_execution item
    assert by_line[4] == ("code_host_fetch", "medium")  # tool/state.input webfetch
    assert 5 not in by_line  # pip install -r requirements.txt


def test_agent_log_fallback_when_no_session_files():
    report = _scan("trial_agentlog")
    assert report["sources"] == ["agent.log"]
    assert report["hits"][0]["rule"] == "code_host_fetch"
    assert report["hits"][0]["severity"] == "high"


def test_unparseable_log_is_not_called_clean():
    report = _scan("trial_empty")
    assert report["verdict"] == "no_tool_calls"
    assert report["needs_review"] is False


def test_missing_transcript(tmp_path):
    report = ts.scan_trial(tmp_path, CASE)
    assert report["verdict"] == "no_transcript"


def test_scan_never_raises(tmp_path):
    report = ts.scan_trial(tmp_path)  # neither case_dir nor rules
    assert report["verdict"] == "error" and "error" in report


# --------------------------------------------------------------------------- wiring


def _result(**kw) -> TrialResult:
    base = dict(case_id="case_widget", backend="claude-code", model="m", reward=1.0, terminal_status="completed")
    base.update(kw)
    return TrialResult(**base)


def test_run_case_records_scan_without_touching_reward(tmp_path):
    from cbrun.run_case import _record_transcript_scan

    trial = tmp_path / "trial"
    shutil.copytree(FIXTURES / "trial_leaky", trial)
    result = _result()
    _record_transcript_scan(trial, result, CASE)
    assert result.reward == 1.0
    assert result.needs_review is True
    assert result.transcript_scan["verdict"] == "needs_review"
    assert result.transcript_scan["flagged"][0]["severity"] == "high"
    written = json.loads((trial / ts.SCAN_REPORT_NAME).read_text())
    assert written["needs_review"] is True
    assert result.logs["transcript_scan"] == str(trial / ts.SCAN_REPORT_NAME)


def test_summary_and_matrix_carry_needs_review(tmp_path):
    flagged = _result(needs_review=True, transcript_scan={"verdict": "needs_review"})
    clean = _result(case_id="case_other", reward=0.0)
    path = write_summary([flagged, clean], tmp_path)
    payload = json.loads(path.read_text())
    assert payload["aggregate"]["needs_review_trials"] == 1
    assert payload["aggregate"]["passed"] == 1
    assert payload["trials"][0]["needs_review"] is True
    assert payload["trials"][0]["transcript_scan"]["verdict"] == "needs_review"
    matrix = format_reward_matrix([flagged, clean])
    assert "PASS(completed)*REVIEW" in matrix


def test_cli_offline_scan(tmp_path, capsys):
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "trial_leaky", run / "case_widget" / "claude-code")
    shutil.copytree(FIXTURES / "trial_clean", run / "case_widget" / "codex")
    out_json = tmp_path / "all.json"
    code = ts.main([str(run), "--cases-root", str(FIXTURES), "--write", "--json", str(out_json)])
    assert code == 1
    text = capsys.readouterr().out
    assert "claude-code: needs_review" in text and "codex: clean" in text
    assert (run / "case_widget" / "claude-code" / ts.SCAN_REPORT_NAME).is_file()
    assert len(json.loads(out_json.read_text())) == 2
