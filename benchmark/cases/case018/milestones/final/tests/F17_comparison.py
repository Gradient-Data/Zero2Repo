# feature: F17
"""Acceptance observations for native binary and function comparison."""
from F07_helpers import symbol_address
from F17_helpers import address_pair, block_address_pairs, comparison_pair


def test_function_correspondence_and_relocation(tmp_path):
    left, right, diff = comparison_pair(tmp_path)
    common = {'_start', 'caller', 'operation', 'constants', 'leaf'}
    expected = {address_pair(left, right, name) for name in common}
    assert set(diff.function_matches) == expected
    removed = symbol_address(left, 'removed')
    assert diff.unmatched_functions == ({removed}, set())
    unchanged = {address_pair(left, right, name) for name in ('_start', 'caller', 'leaf')}
    assert unchanged <= set(diff.identical_functions)
    # Reverse the same comparison to exercise the other unmatched carrier.
    reverse = right.analyses.BinDiff(left, cfg_a=diff.cfg_b, cfg_b=diff.cfg_a)
    assert set(reverse.function_matches) == {(b, a) for a, b in expected}
    assert reverse.unmatched_functions == (set(), {removed})
    assert {(b, a) for a, b in unchanged} <= set(reverse.identical_functions)


def test_matched_block_operation_changes(tmp_path):
    left, right, diff = comparison_pair(tmp_path)
    function_pair = address_pair(left, right, 'operation')
    function_diff = diff.get_function_diff(*function_pair)
    entry = function_pair
    unchanged = address_pair(left, right, 'unchanged_arm')
    changed = address_pair(left, right, 'changed_arm')
    assert block_address_pairs(function_diff.block_matches) == {entry, unchanged, changed}
    assert block_address_pairs(function_diff.identical_blocks) == {entry, unchanged}
    assert block_address_pairs(function_diff.differing_blocks) == {changed}
    assert function_pair in set(diff.differing_functions)

