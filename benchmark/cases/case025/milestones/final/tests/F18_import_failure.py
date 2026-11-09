# feature: F18
"""Source contracts remain checkable when module execution fails."""

from _helpers import workspace
from F01_helpers import reported_findings, assert_findings
from F03_helpers import check_types


def test_failure_and_independent_diagnostics():
    source = (
        'raise RuntimeError("module initialization unavailable")\n'
        'def inspect_source():\n'
        '    valid: int = 23\n'
        '    invalid: int = "text"\n'
        '    return valid, invalid, missing_after_failure\n'
    )
    with workspace({'unavailable.py': source}) as root:
        for args, filename in [
            ([str(root / 'unavailable.py')], str(root / 'unavailable.py')),
            (['--code', source], '<code>'),
        ]:
            result, findings = reported_findings(root, args)
            assert_findings(findings, [
                (filename, 1, 'import_failed'),
                (filename, 4, 'incompatible_assignment'),
                (filename, 5, 'undefined_name'),
            ], sources={filename: source})
            failure, = [f for f in findings if f['code'] == 'import_failed']
            # Only the submitted exception class and payload, not product prose.
            assert 'RuntimeError' in failure['description']
            assert 'module initialization unavailable' in failure['description']
            assert '(code: import_failed)' in result.stderr
            assert 'RuntimeError' in result.stderr
            assert 'module initialization unavailable' in result.stderr


def test_source_declarations_without_runtime_objects():
    check_types('''
        raise RuntimeError("declarations were not executed")  # E: import_failed
        from typing import Generic, TypeVar, TypeAlias, TypedDict, NamedTuple
        from dataclasses import dataclass

        def render(value: int) -> str:
            return str(value)

        class Member:
            count: int

        T = TypeVar("T")
        class Box(Generic[T]):
            value: T
            def __init__(self, value: T) -> None:
                self.value = value

        Labels: TypeAlias = list[str]

        class Record(TypedDict):
            count: int

        class Pair(NamedTuple):
            count: int
            label: str

        @dataclass
        class Entry:
            count: int
            label: str

        def uses(member: Member, box: Box[int], record: Record,
                 pair: Pair, entry: Entry) -> None:
            render(5)
            render("wrong")  # E: incompatible_argument
            rendered: str = render(5)
            wrong_result: int = render(5)  # E: incompatible_assignment
            member.count = 6
            member.count = "wrong"  # E: incompatible_assignment
            member_value: int = member.count
            wrong_member: str = member.count  # E: incompatible_assignment
            Box[int](6)
            Box[int]("wrong")  # E: incompatible_argument
            box_value: int = box.value
            wrong_box: str = box.value  # E: incompatible_assignment
            labels: Labels = ["valid"]
            wrong_labels: Labels = [8]  # E: incompatible_assignment
            mapping: Record = {"count": 9}
            wrong_mapping: Record = {"count": "wrong"}  # E: incompatible_assignment
            record_value: int = record["count"]
            wrong_record: str = record["count"]  # E: incompatible_assignment
            Pair(10, "valid")
            Pair("wrong", "valid")  # E: incompatible_argument
            pair_value: int = pair.count
            wrong_pair: str = pair.count  # E: incompatible_assignment
            Entry(11, "valid")
            Entry("wrong", "valid")  # E: incompatible_argument
            entry_value: int = entry.count
            wrong_entry: str = entry.count  # E: incompatible_assignment
    ''')
