# feature: F11
"""Conditional refinement and pattern matching through the public checker CLI."""
from F03_helpers import check_types


def test_conditions_and_invalidation():
    check_types('''
        from typing import Any, Callable, Literal, assert_type
        from typing_extensions import Sentinel
        MISSING = Sentinel("MISSING")
        class Named:
            name: str
        class Other:
            pass
        def conditions(x: int | str | None, flag: Literal[0, 1, 2],
                       action: object, record: object,
                       cls: type[int] | type[str], item: MISSING | str):
            if isinstance(x, int):
                assert_type(x, int)
                assert_type(x, str)  # E: inference_failure
            else:
                assert_type(x, str | None)
            if x is None:
                assert_type(x, None)
            else:
                assert_type(x, int | str)
            if flag == 1:
                assert_type(flag, Literal[1])
            else:
                assert_type(flag, Literal[0, 2])
            if flag:
                assert_type(flag, Literal[1, 2])
            else:
                assert_type(flag, Literal[0])
            action()  # E: not_callable
            if callable(action):
                assert_type(action, Callable[..., Any])
                action()
            else:
                assert_type(action, object)
                action()  # E: not_callable
            if hasattr(record, 'name'):
                print(record.name)
            else:
                print(record.name)  # E: undefined_attribute
            if issubclass(cls, int):
                assert_type(cls, type[int])
            else:
                assert_type(cls, type[str])
            if item is MISSING:
                assert_type(item, MISSING)
            else:
                assert_type(item, str)
            if x is not None and not isinstance(x, int):
                assert_type(x, str)
            if isinstance(x, int) or x is None:
                assert_type(x, int | None)
            else:
                assert_type(x, str)
            assert x is not None
            assert_type(x, int | str)
            if isinstance(x, int):
                x = 'replacement'
                assert_type(x, Literal['replacement'])
                x + 1  # E: unsupported_operation
    ''')


def test_declared_guards():
    check_types('''
        from typing import Annotated, TypeGuard, assert_type
        from typing_extensions import TypeIs
        from velnora.extensions import ParameterTypeGuard
        def positive(value: int | str) -> TypeGuard[str]:
            return isinstance(value, str)
        def two_sided(value: int | str) -> TypeIs[str]:
            return isinstance(value, str)
        def invalid(value: int) -> TypeIs[str]:  # E: typeis_must_be_subtype
            return False
        def named(first: object, second: object) -> Annotated[bool, ParameterTypeGuard['second', str]]:
            return isinstance(second, str)
        class Guard:
            def check(self, value: object) -> Annotated[bool, ParameterTypeGuard['value', int]]:
                return isinstance(value, int)
        def use(value: int | str, first: object, second: object, guard: Guard):
            if positive(value):
                assert_type(value, str)
            else:
                assert_type(value, int | str)
                assert_type(value, int)  # E: inference_failure
            if two_sided(value):
                assert_type(value, str)
            else:
                assert_type(value, int)
                assert_type(value, str)  # E: inference_failure
            if named(first, second):
                assert_type(first, object)
                assert_type(second, str)
            if guard.check(second):
                assert_type(second, int)
                assert_type(guard, Guard)
    ''')


def test_numeric_and_length_refinement():
    check_types('''
        from typing import Annotated, assert_type
        from typing_extensions import TypedDict, NotRequired
        from annotated_types import Gt, MinLen, MaxLen
        def high(x: Annotated[int, Gt(7)]):
            pass
        def long(x: Annotated[str, MinLen(3)]):
            pass
        def short(x: Annotated[str, MaxLen(3)]):
            pass
        class Small(TypedDict, closed=True):
            a: int
            b: NotRequired[int]
        class Large(TypedDict, closed=True):
            a: int
            b: int
            c: int
        def use(n: int, text: str, values: tuple[int, ...],
                tail: tuple[*tuple[int, ...], str], mapping: Small | Large):
            high(n)  # E: incompatible_argument
            if n > 7:
                high(n)
            if n > 6:
                high(n)  # E: incompatible_argument
            if len(text) == 3:
                long(text)
                short(text)
            if len(text) > 3:
                long(text)
                short(text)  # E: incompatible_argument
            if len(text) < 3:
                short(text)
                long(text)  # E: incompatible_argument
            if len(values) == 2:
                assert_type(values, tuple[int, int])
                assert_type(values, tuple[int])  # E: inference_failure
            if len(tail) >= 2:
                assert_type(tail, tuple[int, *tuple[int, ...], str])
                assert_type(tail, tuple[int, str])  # E: inference_failure
            if len(mapping) < 3:
                assert_type(mapping, Small)
            if len(mapping) > 2:
                assert_type(mapping, Large)
    ''')


def test_structural_patterns():
    check_types('''
        from typing import Literal, assert_type
        class Point:
            __match_args__ = ('label', 'size')
            label: str
            size: int
        def literals(x: Literal[1, 2, 3] | None):
            match x:
                case None:
                    assert_type(x, None)
                case 1 | 2 as found:
                    assert_type(found, Literal[1, 2])
                case remaining:
                    assert_type(remaining, Literal[3])
                    assert_type(remaining, str)  # E: inference_failure
        def sequences(x: tuple[int, ...]):
            match x:
                case [first, second]:
                    assert_type(first, int)
                    assert_type(x, tuple[int, int])
                case [head, *rest]:
                    assert_type(head, int)
                    assert_type(rest, list[int])
        def mappings():
            match {'name': 'oak', 'count': 4}:
                case {'name': name, **rest}:
                    assert_type(name, Literal['oak'])
                    assert_type(rest['count'], Literal[4])
        def classes(x: object):
            match x:
                case Point(label, size) if size == 4:
                    assert_type(x, Point)
                    assert_type(label, str)
                    assert_type(size, Literal[4])
                case Point(size=size):
                    assert_type(size, int)
                case Point(a, b, c):  # E: bad_match
                    pass
                case Point(a, label=b):  # E: bad_match
                    pass
        def impossible(x: int):
            match x:
                case None:  # E: impossible_pattern
                    pass
                case 'text':  # E: impossible_pattern
                    pass
                case _:
                    assert_type(x, int)
    ''')


def test_literal_string_safety():
    check_types('''
        from typing_extensions import LiteralString
        def consume(text: LiteralString) -> LiteralString:
            return text
        def use(left: LiteralString, right: LiteralString, runtime: str):
            consume('constant')
            consume(left)
            consume(f'{left}/{right}')
            consume(f'prefix/{left}/suffix')
            consume(runtime)  # E: incompatible_argument
            consume(f'{left}/{runtime}')  # E: incompatible_argument
            consume(f'{runtime}/{right}')  # E: incompatible_argument
    ''')


def test_dataclass_positional_patterns():
    check_types('''
        from dataclasses import dataclass, field
        from typing import assert_type
        @dataclass
        class Record:
            name: str
            hidden: bool = field(kw_only=True)
            count: int
        @dataclass(match_args=False)
        class KeywordRecord:
            name: str
        def use(record: Record, keyword: KeywordRecord):
            match record:
                case Record(name, count, hidden=hidden):
                    assert_type(name, str)
                    assert_type(count, int)
                    assert_type(hidden, bool)
                    assert_type(count, bool)  # E: inference_failure
            match record:
                case Record(a, b, c):  # E: bad_match
                    pass
            match keyword:
                case KeywordRecord(name=name):
                    assert_type(name, str)
            match keyword:
                case KeywordRecord(name):  # E: bad_match
                    pass
    ''')
