# feature: F19
"""Runtime decisions, explanatory locations, and value restrictions."""
from typing import Annotated

from annotated_types import Gt, MinLen, Predicate
from velnora.runtime import get_assignability_error, is_assignable



def test_runtime_collection_contents():
    cases = [
        (17, int, True), ('seventeen', int, False),
        ('seventeen', str, True), (17, str, False),
        ([], list[int], True), ((), list[int], False),
        ([2, 5, 8], list[int], True), ([2, 5, 'bad'], list[int], False),
        ({}, dict[str, int], True), ([], dict[str, int], False),
        ({'a': 2, 'b': 5}, dict[str, int], True),
        ({'a': 2, 'b': 'bad'}, dict[str, int], False),
        ({'a': 2, 5: 8}, dict[str, int], False),
        (set(), set[int], True), ({2, 5}, set[int], True),
        ({2, 'bad'}, set[int], False),
        ((2, 'oak'), tuple[int, str], True),
        ((2, 5), tuple[int, str], False),
        ([[2], [5, 8]], list[list[int]], True),
        ([[2], [5, 'bad']], list[list[int]], False),
    ]
    for value, annotation, expected in cases:
        assert is_assignable(value, annotation) is expected, (value, annotation)


def test_runtime_explanations():
    for value, annotation in [([], list[int]), ([2, 5], list[int]),
                              ({'oak': 2}, dict[str, int]), (17, int)]:
        assert get_assignability_error(value, annotation) is None
    # Only fixed diagnostic labels are shell; prose and indentation are not.
    labels = ('In element ', 'In key of key-value pair ', 'In value of key-value pair ')

    def located(error):
        return {label for line in error.splitlines() for label in labels
                if line.strip().startswith(label)}

    outer = get_assignability_error(17, list[int])
    assert isinstance(outer, str) and outer.strip()
    assert any(line.strip().startswith('Cannot assign ') for line in outer.splitlines())
    # An outer-type failure is not attributed to a contained position.
    assert located(outer) == set(), outer
    for index in (0, 2):
        values = [2, 5, 8]
        values[index] = 'bad'
        error = get_assignability_error(values, list[int])
        assert isinstance(error, str)
        assert f'In element {index}' in [line.strip() for line in error.splitlines()]
        assert located(error) == {'In element '}, error
    for value, label in [
        ({'oak': 2, 5: 8}, 'In key of key-value pair '),
        ({'oak': 2, 'elm': 'bad'}, 'In value of key-value pair '),
    ]:
        error = get_assignability_error(value, dict[str, int])
        assert isinstance(error, str)
        assert located(error) == {label}, error


def test_runtime_value_restrictions():
    cases = [
        (Annotated[int, Gt(4)], [(3, False), (4, False), (5, True)]),
        (Annotated[str, MinLen(3)], [('ab', False), ('abc', True), ('abcd', True)]),
        (Annotated[str, Predicate(str.islower)], [('oak', True), ('Oak', False)]),
    ]
    for annotation, samples in cases:
        for value, expected in samples:
            assert is_assignable(value, annotation) is expected, (value, annotation)
            error = get_assignability_error(value, annotation)
            if expected:
                assert error is None
            else:
                assert isinstance(error, str) and error.strip(), (value, annotation)


def test_runtime_guard_refinement():
    from F03_helpers import check_types

    # The baseline loses precise metadata after a guard. Check its dependable
    # effect on restricted calls without requiring that implementation defect.
    check_types('''
        from typing import Annotated
        from annotated_types import Predicate
        from velnora.runtime import is_assignable
        Lower = Annotated[str, Predicate(str.islower)]
        def require_lower(value: Lower):
            pass
        def conditional(text: str, other: str):
            require_lower(text)  # E: incompatible_argument
            if is_assignable(text, Lower):
                require_lower(text)
                require_lower(other)  # E: incompatible_argument
        def asserted(text: str, other: str):
            require_lower(text)  # E: incompatible_argument
            assert is_assignable(text, Lower)
            require_lower(text)
            require_lower(other)  # E: incompatible_argument
    ''')
