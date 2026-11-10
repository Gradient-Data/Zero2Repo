# feature: F08
"""Typed mapping acceptance through the source CLI."""
from F03_helpers import check_types


def test_declarations_and_construction():
    check_types('''
        from typing import Generic, TypeVar, ClassVar, assert_type
        from typing_extensions import TypedDict, Required, NotRequired, ReadOnly
        T = TypeVar('T')
        class Base(TypedDict):
            name: str
        class Record(Base, total=False):
            count: int
            active: Required[bool]
        def generic_scope():
            class Box(TypedDict, Generic[T]):
                value: T
            def check(b: Box[int], s: Box[str]):
                assert_type(b['value'], int)
                assert_type(s['value'], str)
                b['value'] = 4
                b['value'] = 'bad'  # E: incompatible_argument
                integer_box: Box[int] = {'value': 3}
                wrong_box: Box[int] = {'value': 'bad'}  # E: incompatible_assignment
        def use():
            Record(name='a', active=True)
            Record(name='a', active=True, count=2)
            Record(active=True)  # E: incompatible_call
            Record(name='a')  # E: incompatible_call
            Record(name='a', active=True, count='bad')  # E: incompatible_argument
            good: Record = {'name': 'a', 'active': True}
            missing: Record = {'active': True}  # E: incompatible_assignment
            wrong: Record = {'name': 2, 'active': True}  # E: incompatible_assignment
            good['name'] = 'b'
            good['name'] = 3  # E: incompatible_argument
            class Optional(TypedDict):
                value: NotRequired[int]
            Optional()
            class Invalid(TypedDict):
                a: 42  # E: invalid_annotation
                b: Required[NotRequired[int]]  # E: invalid_qualifier
                c: Required[Required[int]]  # E: invalid_qualifier
                d: NotRequired[NotRequired[int]]  # E: invalid_qualifier
                e: ReadOnly[ReadOnly[int]]  # E: invalid_qualifier
                f: ClassVar[int]  # E: invalid_qualifier
    ''')


def test_lookup_and_keys():
    check_types('''
        from typing import assert_type
        from typing_extensions import TypedDict
        class Record(TypedDict):
            count: int
            name: str
        class Extra(TypedDict, extra_items=bytes):
            count: int
        def use(r: Record, e: Extra, key: str):
            assert_type(r['count'], int)
            assert_type(r['name'], str)
            assert_type(e['count'], int)
            assert_type(e['payload'], bytes)
            assert_type(r['count'], str)  # E: inference_failure
            r['missing']  # E: invalid_typeddict_key
            r[key]  # E: invalid_typeddict_key
            r[1]  # E: invalid_typeddict_key
            e[1]  # E: invalid_typeddict_key
    ''')


def test_mutation_and_operation_results():
    check_types('''
        from typing import assert_type, Union, Literal
        from typing_extensions import TypedDict, NotRequired, ReadOnly
        class Record(TypedDict):
            count: int
            note: NotRequired[str]
            locked: ReadOnly[NotRequired[int]]
        class Extra(TypedDict, extra_items=int):
            name: str
        def use(r: Record, e: Extra):
            r['count'] = 3
            r['count'] = 'bad'  # E: incompatible_argument
            r.update({'count': 4, 'note': 'ok'})
            r.update({'count': 'bad'})  # E: incompatible_argument
            r['locked'] = 2  # E: readonly_typeddict
            r.update({'locked': 2})  # E: readonly_typeddict
            del r['note']
            del r['count']  # E: incompatible_argument
            del r['locked']  # E: readonly_typeddict
            assert_type(r.pop('note'), str)
            assert_type(r.pop('note', 0), Union[str, Literal[0]])
            r.pop('count')  # E: incompatible_argument
            r.pop('locked')  # E: readonly_typeddict
            assert_type(r.setdefault('note', 'ok'), str)
            r.setdefault('note', 3)  # E: incompatible_argument
            r.setdefault('locked', 1)  # E: readonly_typeddict
            assert_type(r.get('count'), int)
            assert_type(r.get('note', 0), Union[str, Literal[0]])
            assert_type(e.get('other', 'absent'), Union[int, Literal['absent']])
            assert_type(e.pop('other'), int)
            assert_type(e.pop('other', 'absent'), Union[int, Literal['absent']])
            assert_type(e.setdefault('other', 'absent'), Union[int, Literal['absent']])
    ''')


def test_open_closed_and_extra_entries():
    check_types('''
        from typing import assert_type
        from typing_extensions import TypedDict
        class Open(TypedDict):
            name: str
        class Explicit(TypedDict, closed=False):
            name: str
        class Closed(TypedDict, closed=True):
            name: str
        class Larger(TypedDict):
            name: str
            count: int
        class Extra(TypedDict, extra_items=int):
            name: str
        def use(source: Larger, extra: Extra):
            default: Open = source
            explicit: Explicit = source
            closed: Closed = source  # E: incompatible_assignment
            Open(name='a')
            Explicit(name='a')
            Closed(name='a')
            Open(name='a', count=1)  # E: incompatible_call|incompatible_argument
            Explicit(name='a', count=1)  # E: incompatible_call|incompatible_argument
            Closed(name='a', count=1)  # E: incompatible_argument|incompatible_call
            bad_open: Open = {'name': 'a', 'count': 1}  # E: incompatible_assignment
            bad_explicit: Explicit = {'name': 'a', 'count': 1}  # E: incompatible_assignment
            bad_closed: Closed = {'name': 'a', 'count': 1}  # E: incompatible_assignment
            Extra(name='a', count=1)
            Extra(name='a', count='bad')  # E: incompatible_argument
            assert_type(extra['count'], int)
            extra['count'] = 1
            extra['count'] = 'bad'  # E: incompatible_argument
    ''')


def test_structural_assignment_and_redeclaration():
    check_types('''
        from typing_extensions import TypedDict, ReadOnly, NotRequired
        class Writable(TypedDict):
            value: int
        class Narrow(TypedDict):
            value: bool
        class Optional(TypedDict):
            value: NotRequired[int]
        class Read(TypedDict):
            value: ReadOnly[int]
        class ReadOptional(TypedDict):
            value: ReadOnly[NotRequired[int]]
        class Wrong(TypedDict):
            value: str
        def use(w: Writable, n: Narrow, o: Optional, r: Read, ro: ReadOptional, s: Wrong):
            a: Writable = w
            b: Writable = n  # E: incompatible_assignment
            c: Narrow = w  # E: incompatible_assignment
            d: Writable = o  # E: incompatible_assignment
            e: Optional = w  # E: incompatible_assignment
            f: Writable = r  # E: incompatible_assignment
            g: Read = n
            h: Read = w
            i: ReadOptional = w
            j: ReadOptional = o
            k: Read = ro  # E: incompatible_assignment
            l: Read = s  # E: incompatible_assignment
            class Same(Writable):
                value: int
            class BadType(Writable):
                value: bool  # E: invalid_typeddict
            class BadRead(Writable):
                value: ReadOnly[int]  # E: invalid_typeddict
            class BadPresence(Writable):
                value: NotRequired[int]  # E: invalid_typeddict
            class NarrowRead(Read):
                value: ReadOnly[bool]
            class RequiredRead(ReadOptional):
                value: ReadOnly[int]
            class LoseRequired(Read):
                value: ReadOnly[NotRequired[int]]  # E: invalid_typeddict
    ''')


def test_extra_entry_inheritance():
    check_types('''
        from typing_extensions import TypedDict, ReadOnly
        def declarations():
            class Closed(TypedDict, closed=True):
                name: str
            class Mutable(TypedDict, extra_items=int):
                name: str
            class Read(TypedDict, extra_items=ReadOnly[int]):
                name: str
            class Reopen(Closed, closed=False):  # E: invalid_typeddict
                pass
            class Change(Mutable, extra_items=str):  # E: invalid_typeddict
                pass
            class CloseMutable(Mutable, closed=True):  # E: invalid_typeddict
                pass
            class Remove(Mutable, closed=False):  # E: invalid_typeddict
                pass
            class RemoveRead(Read, closed=False):  # E: invalid_typeddict
                pass
            class Narrow(Read, extra_items=ReadOnly[bool]):
                pass
            class CloseRead(Read, closed=True):
                pass
            class Retain(Mutable):
                pass
            Retain(name='a', count=1)
            Retain(name='a', count='bad')  # E: incompatible_argument
            Narrow(name='a', flag=True)
            Narrow(name='a', flag='bad')  # E: incompatible_argument
            CloseRead(name='a')
            CloseRead(name='a', count=1)  # E: incompatible_argument|incompatible_call
    ''')


def test_unpacked_keyword_contract():
    check_types('''
        from typing import assert_type
        from typing_extensions import TypedDict, Unpack, NotRequired
        class Options(TypedDict):
            name: str
            count: NotRequired[int]
        def target(**options: Unpack[Options]) -> str:
            assert_type(options['name'], str)
            assert_type(options['count'], int)
            return options['name']
        def use(valid: Options):
            assert_type(target(name='a'), str)
            target(name='a', count=3)
            target(**valid)
            target(**{'name': 'a', 'count': 2})
            target()  # E: incompatible_call
            target(count=2)  # E: incompatible_call
            target(name=2)  # E: incompatible_argument
            target(name='a', count='bad')  # E: incompatible_argument
            target(**{'name': 2})  # E: incompatible_argument
    ''')
