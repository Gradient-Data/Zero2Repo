# feature: F04
"""Acceptance of refinement annotations through real source checking."""
from F03_helpers import check_types
from F04_helpers import check_extension_source, CUSTOM_CHECKS


def test_intersection_negation_overlap():
    check_types("""
        from typing_extensions import assert_type
        from velnora.extensions import Intersection, Not, Overlapping
        class A: pass
        class B: pass
        class C: pass
        class AB(A, B): pass
        class AC(A, C): pass
        def both(x: Intersection[A, B | C]) -> None: pass
        def excluded(x: Not[int]) -> None: pass
        def reduced(x: Intersection[int | str, Not[str]]) -> None:
            assert_type(x, int)
            assert_type(x, str)  # E: inference_failure
        def overlap(x: Overlapping[int]) -> None: pass
        def use(a: A, ab: AB, ac: AC, mixed: int | str, text: str | bytes) -> None:
            both(ab)
            both(ac)
            both(a)  # E: incompatible_argument
            assigned: Intersection[A, B] = a  # E: incompatible_assignment
            valid: Intersection[A, B] = ab
            excluded('ok')
            excluded(4)  # E: incompatible_argument
            excluded(True)  # E: incompatible_argument
            reduced(7)
            reduced('no')  # E: incompatible_argument
            overlap(mixed)
            overlap(text)  # E: incompatible_argument
    """)


def test_extended_and_strict_literals():
    source = """
        from enum import Enum
        from typing_extensions import Literal
        class Color(Enum):
            BLUE = 1
        def signature(x: int) -> str: return str(x)
        def equivalent(x: int) -> str: return str(x + 1)
        def wrong(x: str) -> int: return len(x)
        def callable_value(x: Literal[signature]) -> None: pass
        def runtime_value(x: Literal[2.5]) -> None: pass
        def class_value(x: Literal[object]) -> None: pass
        def ordinary(a: Literal[3], b: Literal['s'], c: Literal[b'b'],
                     d: Literal[True], e: Literal[Color.BLUE], f: Literal[None]) -> None: pass
        def use() -> None:
            callable_value(equivalent)
            callable_value(wrong)  # E: incompatible_argument
            runtime_value(2.5)
            runtime_value(3.5)  # E: incompatible_argument
            class_value(object)
            ordinary(3, 's', b'b', True, Color.BLUE, None)
    """
    check_extension_source(source)
    check_extension_source(source, options=['--enable', 'invalid_literal'],
                           extra_errors={8: 'invalid_literal', 9: 'invalid_literal',
                                         10: 'invalid_literal'})


def test_custom_assignment_checks():
    findings = check_extension_source("""
        from typing import Any, TypeVar, Generic
        from typing_extensions import Annotated, Literal
        from restrictions import Incoming, Outgoing, Matches
        def incoming(x: Annotated[int, Incoming()]) -> None: pass
        def text(x: str) -> None: pass
        def anything(x: Any) -> None: pass
        T = TypeVar('T')
        class Box(Generic[T]):
            def accept(self, x: Annotated[object, Matches(T)]) -> None: pass
        def use(secret: Annotated[str, Outgoing()], box: Box[Literal[7]], other: Box[Literal[9]]) -> None:
            incoming(8)
            incoming(0)  # E: incompatible_argument
            text(secret)
            anything(secret)  # E: incompatible_argument
            box.accept(7)
            box.accept(9)  # E: incompatible_argument
            other.accept(9)
            other.accept(7)  # E: incompatible_argument
            transparent: Annotated[int, 'documentation only'] = 4
            plain: int = transparent
            invalid: Annotated[int, 'documentation only'] = 'bad'  # E: incompatible_assignment
    """, provider=CUSTOM_CHECKS)
    reasons = {12: 'incoming-zero-forbidden', 14: 'outgoing-unknown-forbidden',
               16: 'specialized-value-required', 18: 'specialized-value-required'}
    for line, reason in reasons.items():
        finding, = [f for f in findings if f['lineno'] == line]
        assert reason in finding['concise_message'], finding


def test_literal_only_and_no_any():
    check_types("""
        from typing import Any
        from typing_extensions import Annotated
        from velnora.extensions import LiteralOnly, NoAny
        def literal(x: Annotated[str, LiteralOnly()]) -> None: pass
        def shallow(x: Annotated[list[int], NoAny()]) -> None: pass
        def deep(x: Annotated[list[int], NoAny(deep=True)]) -> None: pass
        def use(s: str, unknown: Any, nested: list[Any], concrete: list[int]) -> None:
            literal('known')
            literal(s)  # E: incompatible_argument
            literal(unknown)  # E: incompatible_argument
            shallow(unknown)  # E: incompatible_argument
            shallow(nested)
            shallow(concrete)
            deep(unknown)  # E: incompatible_argument
            deep(nested)  # E: incompatible_argument
            deep(concrete)
    """)


def test_numeric_bounds():
    check_extension_source("""
        from typing import Any
        from typing_extensions import Annotated
        from annotated_types import Gt, Ge, Lt, Le
        from restrictions import above_metadata, below_metadata
        Above = Annotated[float, above_metadata]
        AtMost = Annotated[float, below_metadata]
        def gt(x: Annotated[float, Gt(5)]) -> None: pass
        def ge(x: Annotated[float, Ge(5)]) -> None: pass
        def lt(x: Annotated[float, Lt(5)]) -> None: pass
        def le(x: Annotated[float, Le(5)]) -> None: pass
        def use(raw: float, unknown: Any, lower: Annotated[float, Gt(4)],
                upper: Annotated[float, Lt(6)], strict: Annotated[float, Gt(5)],
                inclusive: Annotated[float, Ge(5)], high: Annotated[float, Ge(6)],
                small: Annotated[float, Le(4)], upper_strict: Annotated[float, Lt(5)],
                upper_inclusive: Annotated[float, Le(5)]) -> None:
            gt(5)  # E: incompatible_argument
            gt(5.25)
            ge(5)
            ge(4.75)  # E: incompatible_argument
            lt(5)  # E: incompatible_argument
            lt(4.75)
            le(5)
            le(5.25)  # E: incompatible_argument
            gt(raw)  # E: incompatible_argument
            ge(raw)  # E: incompatible_argument
            lt(raw)  # E: incompatible_argument
            le(raw)  # E: incompatible_argument
            gt(unknown)
            ge(unknown)
            lt(unknown)
            le(unknown)
            gt(strict)
            ge(strict)
            gt(inclusive)  # E: incompatible_argument
            ge(inclusive)
            gt(high)
            ge(lower)  # E: incompatible_argument
            lt(small)
            le(small)
            lt(upper_strict)
            le(upper_strict)
            lt(upper_inclusive)  # E: incompatible_argument
            le(upper_inclusive)
            le(upper)  # E: incompatible_argument
            assigned: Above = 5  # E: incompatible_assignment
            valid: AtMost = 5
    """, provider="from annotated_types import Gt, Le\nabove_metadata = Gt(5)\nbelow_metadata = Le(5)\n")


def test_timezone_restrictions():
    check_types("""
        from datetime import datetime, timezone, timedelta
        from typing import Any
        from typing_extensions import Annotated
        from annotated_types import Timezone
        naive = datetime(2024, 1, 2)
        utc = datetime(2024, 1, 2, tzinfo=timezone.utc)
        offset = datetime(2024, 1, 2, tzinfo=timezone(timedelta(hours=2)))
        def no_tz(x: Annotated[object, Timezone(None)]) -> None: pass
        def aware(x: Annotated[object, Timezone(...)]) -> None: pass
        def fixed(x: Annotated[object, Timezone(timezone.utc)]) -> None: pass
        def use(raw: datetime, unknown: Any, proven: Annotated[datetime, Timezone(timezone.utc)],
                absent: Annotated[datetime, Timezone(None)]) -> None:
            no_tz(naive)
            no_tz(utc)  # E: incompatible_argument
            aware(naive)  # E: incompatible_argument
            aware(utc)
            aware(offset)
            fixed(utc)
            fixed(offset)  # E: incompatible_argument
            fixed(naive)  # E: incompatible_argument
            no_tz(raw)  # E: incompatible_argument
            aware(raw)  # E: incompatible_argument
            fixed(raw)  # E: incompatible_argument
            no_tz(unknown)
            aware(unknown)
            fixed(unknown)
            no_tz(1)  # E: incompatible_argument
            aware(1)  # E: incompatible_argument
            fixed(1)  # E: incompatible_argument
            aware(proven)
            fixed(proven)
            no_tz(absent)
            aware(absent)  # E: incompatible_argument
    """)


def test_external_type_references():
    check_extension_source("""
        from velnora.extensions import ExternalType
        from restrictions import sample_path
        def path(x: ExternalType['pathlib.Path']) -> None: pass
        def text(x: ExternalType['builtins.str']) -> str:
            return x
        def use() -> None:
            text('resolved')
            text(23)  # E: incompatible_argument
            path(sample_path)
            path('not a path object')  # E: incompatible_argument
        def invalid(x: ExternalType['builtins.NoSuchPublicType']) -> None:  # E: invalid_annotation
            pass
    """, provider="from pathlib import Path\nsample_path = Path('/tmp')\n")


def test_divisibility():
    # Python's remainder operation is the PRD's independent standard oracle.
    calls = []
    for value in (0, 12, -12, 13, 1.5, 0.5):
        suffix = '' if value % 3 == 0 else '  # E: incompatible_argument'
        calls.append(f'    multiple({value!r}){suffix}')
    check_types("""from typing import Any
from typing_extensions import Annotated
from annotated_types import MultipleOf
def multiple(x: Annotated[float, MultipleOf(3)]) -> None: pass
def use(raw: float, unknown: Any, strong: Annotated[float, MultipleOf(6)],
        same: Annotated[float, MultipleOf(3)], weak: Annotated[float, MultipleOf(2)]) -> None:
    multiple(raw)  # E: incompatible_argument
    multiple(unknown)
    multiple(strong)
    multiple(same)
    multiple(weak)  # E: incompatible_argument
""" + '\n'.join(calls))


def test_length_restrictions():
    check_types("""
        from typing import Any
        from typing_extensions import Annotated
        from annotated_types import MinLen, MaxLen
        def minimum(x: Annotated[object, MinLen(3)]) -> None: pass
        def maximum(x: Annotated[object, MaxLen(3)]) -> None: pass
        def use(raw: str, unknown: Any, longer: Annotated[str, MinLen(4)],
                shorter: Annotated[str, MaxLen(2)], weak_min: Annotated[str, MinLen(2)],
                weak_max: Annotated[str, MaxLen(4)]) -> None:
            minimum('ab')  # E: incompatible_argument
            minimum('abc')
            minimum('abcd')
            maximum('ab')
            maximum('abc')
            maximum('abcd')  # E: incompatible_argument
            minimum(raw)  # E: incompatible_argument
            maximum(raw)  # E: incompatible_argument
            minimum(unknown)
            maximum(unknown)
            minimum(longer)
            maximum(shorter)
            minimum(weak_min)  # E: incompatible_argument
            maximum(weak_max)  # E: incompatible_argument
            minimum((1, 2))  # E: incompatible_argument
            minimum((1, 2, 3))
            maximum((1, 2, 3))
            maximum((1, 2, 3, 4))  # E: incompatible_argument
    """)


def test_value_predicate():
    findings = check_types("""
        from typing import Any
        from typing_extensions import Annotated
        from annotated_types import Predicate
        def permitted(value: object) -> bool:
            if value == 'explode':
                raise ValueError('predicate-domain-failure')
            return value == 'accepted'
        def restricted(x: Annotated[object, Predicate(permitted)]) -> None: pass
        def use(raw: str, unknown: Any) -> None:
            restricted('accepted')
            restricted('rejected')  # E: incompatible_argument
            restricted('explode')  # E: incompatible_argument
            restricted(raw)  # E: incompatible_argument
            restricted(unknown)
    """)
    failure, = [f for f in findings if f['lineno'] == 12]
    assert 'ValueError' in failure['concise_message'], failure
    assert 'predicate-domain-failure' in failure['concise_message'], failure
