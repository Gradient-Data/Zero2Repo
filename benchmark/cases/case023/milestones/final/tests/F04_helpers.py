# feature: F04
"""Assemble Boolean-language observations through the existing public driver."""

from F01_helpers import operation, pattern_request, assert_success_cases
from F03_helpers import MODES, option_request


def assert_boolean_languages(driver, scenarios):
    """Check explicit membership and search outcomes, including success carriers.

    Each scenario is (pattern, whole-input membership rows, search-span rows).
    Expected results are supplied independently; this helper evaluates no regex.
    """
    cases = []
    for pattern, members, searches in scenarios:
        actions = [operation("is_full_match", data) for data, _ in members]
        expected = [accepted for _, accepted in members]
        actions.extend(operation("find_all", data) for data, _ in searches)
        expected.extend(spans for _, spans in searches)
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(driver, cases)


def assert_boolean_languages_in_modes(driver, scenarios):
    """Repeat whole-input membership rows under every character-coverage mode."""
    cases = []
    for pattern, members in scenarios:
        actions = [operation("is_full_match", data) for data, _ in members]
        expected = [accepted for _, accepted in members]
        for mode in MODES:
            cases.append((option_request(pattern, actions, mode), expected))
    assert_success_cases(driver, cases)
