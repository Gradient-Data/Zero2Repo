# feature: F12
"""Acceptance coverage for language and library recognition."""
from F12_helpers import (language_project, zero_language_project, local_signature,
    signature_project, comparison_project, comparison_matches)


def test_compilation_unit_languages(tmp_path):
    for code, language in (
        (0x000c, "c"), (0x001c, "rust"),
        (0x0016, "go"), (0x001e, "swift"),
    ):
        project = language_project(tmp_path, code)
        detector = project.analyses.LanguageDetector()
        assert detector.language == language
        unit, = project.loader.main_object.compilation_units
        evidence = [entry.partition(':') for entry in detector.evidence]
        assert any(label == 'dwarf_language' and value.strip() == unit.language
                   for label, separator, value in evidence if separator)


def test_unknown_language_without_evidence(tmp_path):
    assert language_project(tmp_path, 0x000c).analyses.LanguageDetector().language == "c"
    assert zero_language_project().analyses.LanguageDetector().language == "unknown"


def test_local_signature_constraints(tmp_path):
    project, cfg, addresses = signature_project(tmp_path)
    original_names = {key: cfg.functions[addresses[key]].name
                      for key in ("wrong_ref", "wrong_byte")}
    result = project.analyses.Flirt(str(local_signature(tmp_path)))
    suggestions = {addr: name for _, mapping in result.matched_suggestions.values()
                   for addr, name in mapping.items()}
    assert suggestions[addresses["good"]] == "recognized_wrapper"
    assert cfg.functions[addresses["good"]].name == "recognized_wrapper"
    for key in ("wrong_ref", "wrong_byte"):
        assert cfg.functions[addresses[key]].name == original_names[key]
        assert addresses[key] not in suggestions


def test_behavioral_comparison_operations(tmp_path):
    project, cfg, addresses = comparison_project(tmp_path)
    matches = comparison_matches(project, cfg)
    for index, operation in enumerate(("memcmp", "strcmp", "strncmp", "strcasecmp")):
        assert matches[addresses[f"f{index}"]] == operation
        assert list(cfg.functions.callgraph.predecessors(addresses[f"f{index}"])) == []
    assert addresses["f4"] not in matches
    # Without the request to include them, functions lacking callers stay unmatched.
    excluded = comparison_matches(project, cfg, require_predecessors=True)
    assert not set(excluded) & {addresses[f"f{index}"] for index in range(4)}


def test_recovered_function_count_limit(tmp_path):
    for total in (400, 401):
        directory = tmp_path / str(total)
        directory.mkdir()
        project, cfg, addresses = comparison_project(directory, total)
        assert set(addresses.values()) <= {f.addr for f in cfg.functions.values()}
        assert len(cfg.functions) == total
        matches = comparison_matches(project, cfg)
        if total == 400:
            assert matches[addresses["f0"]] == "memcmp"
        else:
            assert matches == {}
