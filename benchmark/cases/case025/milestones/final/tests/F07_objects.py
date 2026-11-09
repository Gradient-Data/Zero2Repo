# feature: F07
"""Object contracts exercised through the public source-checking CLI."""
from F03_helpers import check_types


def test_member_access_and_writes():
    check_types('''
        import sys
        from typing import assert_type, overload, Literal
        class Descriptor:
            @overload
            def __get__(self, instance: None, owner: type) -> 'Descriptor': ...
            @overload
            def __get__(self, instance: object, owner: type) -> str: ...
            def __get__(self, instance, owner):
                return self if instance is None else 'text'
            def __set__(self, instance: object, value: str) -> None: pass
        class Base:
            count: int
            runtime = b'data'
            descriptor = Descriptor()
            @property
            def label(self) -> str: return 'label'
            def convert(self, x: int) -> bytes: return bytes(x)
        class Child(Base): pass
        def use(c: Child, number: int):
            assert_type(sys.version, str)
            assert_type(c.count, int)
            assert_type(Base.runtime, Literal[b'data'])
            assert_type(c.runtime, Literal[b'data'])
            assert_type(c.label, str)
            assert_type(c.descriptor, str)
            assert_type(c.convert(2), bytes)
            c.count = 2
            c.count = 'bad'  # E: incompatible_assignment
            c.label = 'bad'  # E: incompatible_assignment
            sys.absent_member  # E: undefined_attribute
            number.absent_member  # E: undefined_attribute
    ''')

    check_types('''
        def declarations():
            class Descriptor:
                def __get__(self, instance: object, owner: type) -> str: return 'text'
                def __set__(self, instance: object, value: str) -> None: pass
            class Holder:
                data = Descriptor()
            def use(h: Holder):
                h.data = 'text'
                h.data = 3  # E: incompatible_assignment
    ''')


def test_concrete_receiver():
    check_types('''
        from typing import Self, assert_type
        class Base:
            def copy(self) -> Self: return self
            @classmethod
            def make(cls) -> Self: return cls()
        class Child(Base): pass
        def use(c: Child):
            assert_type(c.copy(), Child)
            assert_type(Child.make(), Child)
            assert_type(c.copy(), Base)  # E: inference_failure
        def outside(x: Self): pass  # E: invalid_self_usage
        class Invalid:
            @staticmethod
            def static(x: Self): pass  # E: invalid_self_usage
    ''')


def test_structural_interfaces():
    check_types('''
        from typing import Protocol, TypeVar
        T = TypeVar('T', covariant=True)
        class Reader(Protocol[T]):
            def read(self) -> T: ...
        class TextReader:
            def read(self) -> str: return 'text'
        class WrongReader:
            def read(self, required: int) -> str: return 'text'
        class Missing: pass
        class Writable(Protocol):
            value: object
        class Readable(Protocol):
            @property
            def value(self) -> object: ...
        class Narrow:
            value: str
        def read_text(r: Reader[str]): pass
        def read_int(r: Reader[int]): pass
        def use(n: Narrow):
            read_text(TextReader())
            read_int(TextReader())  # E: incompatible_argument
            read_text(WrongReader())  # E: incompatible_argument
            read_text(Missing())  # E: incompatible_argument
            r: Reader[str] = TextReader()
            bad: Reader[int] = TextReader()  # E: incompatible_assignment
            ro: Readable = n
            rw: Writable = n  # E: incompatible_assignment
    ''')


def test_final_and_optional_overrides():
    from F07_helpers import check_object_options
    source = '''
        from typing import Final, final
        class Base:
            value: int
            def method(self, x: int) -> int: return x
            @final
            def sealed(self) -> None: pass
        class Child(Base):
            value: str
            def method(self, x: str) -> str: return x
            def sealed(self) -> None: pass
        @final
        class Closed: pass
        class Forbidden(Closed): pass
        def use():
            x: Final[int] = 1
            x = 2
    '''
    required = [(13, 'invalid_base'),
                (16, 'incompatible_assignment')]
    quiet = ['--disable', 'unused_assignment']
    check_object_options(source, flags=quiet, expected=required)
    check_object_options(source, flags=quiet + ['--enable', 'incompatible_override'],
                         expected=required + [(10, 'incompatible_override'), (8, 'incompatible_override'),
                                              (9, 'incompatible_override')])
    # With the two default findings suppressed, the same file is a clean run.
    check_object_options(source, flags=quiet + ['--disable', 'invalid_base',
                                                '--disable', 'incompatible_assignment'])


def test_class_declaration_validation():
    check_types('''
        from abc import ABC, abstractmethod
        from typing import Generic, TypeVar, TYPE_CHECKING
        from typing_extensions import override
        T = TypeVar('T')
        U = TypeVar('U')
        def declarations():
            class Abstract(ABC):
                @abstractmethod
                def run(self) -> int: ...
            class Concrete(Abstract):
                @override
                def run(self) -> int: return 1
                @override
                def absent(self): pass  # E: override_does_not_override
            @override
            def outside(): pass  # E: invalid_override_decorator
            def use():
                Concrete()
                Abstract()  # E: incompatible_call
        if TYPE_CHECKING:
            class Repeated(Generic[T, T]): pass  # E: invalid_base
            class Root(Generic[T, U]): pass
            class Parent(Root[T, U]): pass
            class Conflict(Parent[T, U], Root[U, T]): pass  # E: invalid_base
            class Meta(type, Generic[T]): pass
            class Good(metaclass=type): pass
            class Specialized(metaclass=Meta[int]): pass  # E: invalid_metaclass
            class Invalid(metaclass=42): pass  # E: invalid_metaclass
    ''')


def test_enumeration_identity_and_values():
    check_types('''
        from enum import Enum
        from typing import Literal, assert_type
        class Color(Enum):
            _value_: int
            RED = 3
            BLUE = 8
        class Duplicate(Enum):
            FIRST = 5
            SECOND = 5  # E: duplicate_enum_member
        class Invalid(Enum):
            _value_: int
            BAD = 'bad'  # E: invalid_annotation
        def use(c: Color):
            assert_type(Color.RED, Literal[Color.RED])
            assert_type(Color.BLUE, Literal[Color.BLUE])
            value: int = c.value
            wrong: str = c.value  # E: incompatible_assignment
            assert_type(Color.RED, int)  # E: inference_failure
            for member in Color:
                assert_type(member, Color)
    ''')


def test_slots_and_missing_attributes():
    from F07_helpers import check_object_options
    check_types('''
        class Base:
            __slots__ = ('base',)
        class Closed(Base):
            __slots__ = ('child',)
        class OpenBase: pass
        class Open(OpenBase):
            __slots__ = ('child',)
        def use(c: Closed, o: Open):
            c.base = 1
            c.child = 2
            c.absent = 3  # E: incompatible_assignment
            o.extra = 4
    ''')
    source = '''
        class Parent:
            declared: int
            def __init__(self): self.assigned = 1
        class Child(Parent): pass
        def use(c: Child):
            print(c.declared, c.assigned)
            print(c.absent)
    '''
    check_object_options(source, flags=['--enable', 'attribute_is_never_set'],
                         expected=[(7, 'attribute_is_never_set')])


def test_readonly_initialization_receivers():
    check_types('''
        from typing import ClassVar
        from typing_extensions import ReadOnly
        class Record:
            value: ReadOnly[int]
            token: ClassVar[ReadOnly[str]]
            def __init__(self, other: 'Record'):
                self.value = 1
                other.value = 2  # E: incompatible_assignment
            def __new__(cls, other: 'Record') -> 'Record':
                obj: Record = object.__new__(cls)
                obj.value = 3
                return obj
            @classmethod
            def reset(cls, obj: 'Record'):
                obj.value = 4
            def __init_subclass__(cls):
                cls.token = 'ready'
            def mutate(self):
                self.value = 5  # E: incompatible_assignment
                del self.value  # E: incompatible_assignment
        class Child(Record):
            def __init__(self): self.value = 6
        class Other:
            value: ReadOnly[int]
        class Factory:
            @classmethod
            def make(cls, obj: Other):
                obj.value = 7  # E: incompatible_assignment
        def use(r: Record):
            r.value = 8  # E: incompatible_assignment
            del r.value  # E: incompatible_assignment
    ''')


def test_qualifier_contexts_and_nesting():
    check_types('''
        from typing import TYPE_CHECKING, ClassVar, Final, TypedDict
        from typing_extensions import ReadOnly, Required, NotRequired
        from dataclasses import dataclass
        if TYPE_CHECKING:
            class Valid:
                shared: ClassVar[int]
                value: ReadOnly[str]
                def __init__(self):
                    self.inline: ReadOnly[int] = 1
            class Mapping(TypedDict):
                required: Required[int]
                optional: NotRequired[str]
                readonly: ReadOnly[int]
            def invalid(a: ClassVar[int], b: Required[int], c: NotRequired[int], d: ReadOnly[int]) -> ReadOnly[int]:  # E: invalid_qualifier, invalid_qualifier, invalid_qualifier, invalid_qualifier, invalid_qualifier
                local: ReadOnly[int] = 1  # E: invalid_qualifier
                cv: ClassVar[int] = 1  # E: invalid_qualifier
                req: Required[int] = 1  # E: invalid_qualifier
                opt: NotRequired[int] = 1  # E: invalid_qualifier
                return 1
            class Invalid:
                required: Required[int]  # E: invalid_qualifier
                optional: NotRequired[int]  # E: invalid_qualifier
                repeated: Final[Final[int]] = 1  # E: invalid_qualifier
                first: Final[ReadOnly[int]] = 1  # E: invalid_qualifier
                second: ReadOnly[Final[int]] = 1  # E: invalid_qualifier
                cvf: ClassVar[Final[int]] = 1  # E: invalid_qualifier
                fcv: Final[ClassVar[int]] = 1  # E: invalid_qualifier
                arity: ClassVar[int, str]  # E: invalid_annotation
                final_arity: Final[int, str] = 1  # E: invalid_annotation
            @dataclass
            class Data:
                valid: ClassVar[Final[int]] = 1
                invalid: Final[ClassVar[int]] = 1  # E: invalid_qualifier
            class InvalidMapping(TypedDict):
                req: Required[int, str]  # E: invalid_annotation
                opt: NotRequired[int, str]  # E: invalid_annotation
                ro: ReadOnly[int, str]  # E: invalid_annotation
    ''')


def test_generated_integer_enumerations():
    check_types('''
        from typing import SupportsIndex
        class Status:
            READY = 2
            DONE = 9
            _VALUES_TO_NAMES = {2: 'READY', 9: 'DONE'}
            _NAMES_TO_VALUES = {'READY': 2, 'DONE': 9}
        def accept(s: Status): pass
        def integer(i: int): pass
        def index(i: SupportsIndex): pass
        def use(s: Status, unknown: int):
            accept(Status.READY)
            accept(Status.DONE)
            accept(2)
            accept(9)
            accept(s)
            accept(unknown)
            accept(3)  # E: incompatible_argument
            accept('READY')  # E: incompatible_argument
            integer(s)
            index(s)
    ''')


def test_specialized_inherited_members():
    check_types('''
        from typing import Generic, TypeVar, assert_type
        T = TypeVar('T')
        class Base(Generic[T]):
            value: T
            def get(self) -> T: return self.value
        class Middle(Base[list[T]]): pass
        class Text(Middle[str]): pass
        def use(t: Text):
            assert_type(t.value, list[str])
            assert_type(t.get(), list[str])
            t.value = ['text']
            t.value = [1]  # E: incompatible_assignment
            assert_type(t.value, list[int])  # E: inference_failure
    ''')


def test_readonly_nested_protocol_and_intersection():
    check_types('''
        from typing import Protocol
        from typing_extensions import ReadOnly
        from velnora.extensions import Intersection
        class Readonly:
            value: ReadOnly[int]
            def __init__(self):
                self.value = 1
                def nested():
                    self.value = 2  # E: incompatible_assignment
                nested()
        class Interface(Protocol):
            value: ReadOnly[int]
            def __init__(self):
                self.value = 1  # E: incompatible_assignment
        class Initialized(Protocol):
            value: ReadOnly[int] = 1  # E: incompatible_assignment
        class Concrete(Interface):
            def __init__(self): self.value = 3
        class Mutable:
            value: int
        def use(obj: Intersection[Readonly, Mutable], ro: Readonly):
            obj.value = 4
            obj.value = 'bad'  # E: incompatible_assignment
            ro.value = 4  # E: incompatible_assignment
    ''')
