# feature: F10
"""Record contracts observed through the public source-checking CLI."""
from F03_helpers import check_types
from _helpers import workspace
from F02_helpers import config_file, check_configured
from textwrap import dedent


def test_namedtuple_fields_and_declarations():
    check_types('''
        from typing import NamedTuple, assert_type
        class Reading(NamedTuple):
            count: int
            label: str = 'unit'
        def use(n: int, s: str):
            r = Reading(n)
            Reading(count=n, label=s)
            assert_type(r.count, int)
            assert_type(r.label, str)
            assert_type(r[0], int)
            assert_type(r[-1], str)
            count, label = r
            assert_type(count, int)
            assert_type(label, str)
            Reading(s)  # E: incompatible_argument
            Reading()  # E: incompatible_call
            Reading(n, n)  # E: incompatible_argument
            r.count = n  # E: incompatible_assignment
            del r.label  # E: incompatible_assignment
            assert_type(r.count, str)  # E: inference_failure
        def declarations():
            class Hidden(NamedTuple):
                _count: int  # E: invalid_namedtuple
            class BadOrder(NamedTuple):
                label: str = 'unit'
                count: int  # E: invalid_namedtuple
            BadName = NamedTuple('BadName', [('not-valid', int)])  # E: incompatible_call
            class BadType(NamedTuple):
                value: 42  # E: invalid_annotation
    ''')


def test_namedtuple_generated_operations_preserve_subclass():
    declaration = dedent('''
        from typing import NamedTuple
        class Entry(NamedTuple):
            number: int
            text: str
        class Tagged(Entry):
            tag: str = 'extra'
    ''').lstrip()
    source = dedent('''
        from typing import Any, assert_type
        def check():
            from records import Entry, Tagged
            def use(value: Tagged):
                assert_type(value._replace(number=1), Tagged)
                assert_type(Tagged._make([1, 'label']), Tagged)
                assert_type(value._asdict(), dict[str, Any])
                assert_type(value._replace(number=1), Entry)
    ''').lstrip()
    with workspace({'records.py': '',
                    'stubs/records-stubs/__init__.pyi': declaration,
                    'use.py': source}) as root:
        config = config_file(root, 'import_paths = ["."]\nstub_path = ["stubs"]\nunused_variable = false\n')
        check_configured(root, config, [root / 'use.py'], expected=[
            ('use.py', 8, 'inference_failure'),
        ])
    check_types('''
        from typing import NamedTuple, assert_type
        class Entry(NamedTuple):
            number: int
            text: str
        class Tagged(Entry):
            tag: str = 'extra'
        def use(value: Tagged, n: int, s: str):
            assert_type(value.tag, str)
            a, b = value
            assert_type(a, int)
            assert_type(b, str)
            Tagged(n, s)
            Tagged(n, s, s)  # E: incompatible_call
            Tagged(n, s, tag=s)  # E: incompatible_call
            _a, _b, _c = value  # E: bad_unpack
    ''')


def test_dataclass_construction_and_initialization():
    check_types('''
        from dataclasses import dataclass, field, InitVar
        from typing import ClassVar, assert_type
        @dataclass
        class Base:
            first: int
            second: str
        @dataclass
        class Record(Base):
            first: int
            third: bytes
            count: int = 0
            items: list[str] = field(default_factory=list)
            internal: int = field(init=False)
            category: ClassVar[str] = 'record'
        @dataclass(kw_only=True)
        class Keywords:
            positional: int = field(kw_only=False)
            required: str
            optional: int = 0
        @dataclass
        class WithInit:
            seed: InitVar[str]
            value: int = field(init=False)
            def __post_init__(self, seed: str):
                self.value = len(seed)
        def use(n: int, s: str, b: bytes, r: Record, w: WithInit):
            Record(n, s, b)
            Record(first=n, second=s, third=b, items=[s])
            assert_type(r.first, int)
            assert_type(r.second, str)
            assert_type(r.third, bytes)
            assert_type(r.items, list[str])
            Record(n, s)  # E: incompatible_call
            Record(s, n, b)  # E: incompatible_argument, incompatible_argument
            Record(n, s, b, items=[n])  # E: incompatible_argument
            Record(n, s, b, internal=n)  # E: incompatible_call
            Record(n, s, b, category=s)  # E: incompatible_call
            Keywords(n, required=s)
            Keywords(positional=n, required=s)
            Keywords(n)  # E: incompatible_call
            Keywords(n, s)  # E: incompatible_call
            WithInit(s)
            WithInit(n)  # E: incompatible_argument
            assert_type(w.value, int)
            w.seed  # E: undefined_attribute
        def invalid_declarations():
            @dataclass
            class BadDefault:
                value: int = 'wrong'  # E: incompatible_assignment
            @dataclass
            class BadFieldDefault:
                value: int = field(default='wrong')  # E: incompatible_assignment
            @dataclass
            class BadFactory:
                value: int = field(default_factory=str)  # E: incompatible_assignment
            @dataclass  # E+3: invalid_dataclass
            class BadOrder:
                first: int = 0
                second: str
            @dataclass  # E+3: invalid_dataclass
            class BadFieldOrder:
                first: int = field(default=0)
                second: str
    ''')
    from F07_helpers import check_object_options
    source = '''
        from dataclasses import dataclass, InitVar
        @dataclass
        class RuntimeGood:
            seed: InitVar[str]
            def __post_init__(self, seed: str) -> None: pass
        @dataclass
        class RuntimeBad:
            seed: InitVar[str]
            def __post_init__(self, seed: int) -> None: pass
        def declarations():
            @dataclass
            class LocalGood:
                seed: InitVar[str]
                def __post_init__(self, seed: str) -> None: pass
            @dataclass
            class LocalBad:
                seed: InitVar[str]
                def __post_init__(self, seed: int) -> None: pass
    '''
    check_object_options(source)
    check_object_options(source, flags=['--enable', 'incompatible_override'],
                         expected=[(9, 'incompatible_override'),
                                   (18, 'incompatible_override')])


def test_dataclass_mutability_slots_and_ordering():
    check_types('''
        from dataclasses import dataclass
        from typing import assert_type
        def declarations():
            @dataclass
            class Mutable:
                value: int
            @dataclass(frozen=True)
            class Frozen:
                value: int
            @dataclass(slots=True)
            class Slotted:
                value: int
                def update(self):
                    self.value = 3
                    self.extra = 3  # E: incompatible_assignment
            @dataclass(order=True)
            class Ordered:
                value: int
            @dataclass(order=True)
            class Other:
                value: int
            def use(m: Mutable, f: Frozen, a: Ordered, b: Ordered, c: Other):
                m.value = 3
                f.value = 3  # E: incompatible_assignment
                m < m  # E: unsupported_operation
                a < b
                a <= b
                a > b
                a >= b
                a < c  # E: unsupported_operation
                a <= c  # E: unsupported_operation
                a > c  # E: unsupported_operation
                a >= c  # E: unsupported_operation
    ''')


def test_dataclass_transform_providers_and_fields():
    check_types('''
        from typing import Any, TypeVar, assert_type
        from typing_extensions import dataclass_transform
        T = TypeVar('T')
        def column(*, default: Any = ..., alias: str | None = None,
                   kw_only: bool = False, init: bool = True) -> Any:
            return object()
        @dataclass_transform(field_specifiers=(column,), kw_only_default=True,
                             frozen_default=True)
        def record(cls: type[T]) -> type[T]:
            return cls
        @record
        class Decorated:
            value: int = column(alias='amount')
            label: str = column(default='unit', kw_only=False)
            excluded: int = column(init=False)
        @dataclass_transform()
        class Base:
            pass
        class Derived(Base):
            value: str
            count: int = 0
        @dataclass_transform()
        class Meta(type):
            pass
        class MetaRecord(metaclass=Meta):
            value: bytes
        def use(d: Decorated, b: Derived, m: MetaRecord):
            Decorated(amount=1)
            Decorated('label', amount=1)
            Decorated()  # E: incompatible_call
            Decorated(value=1)  # E: incompatible_call
            Decorated(amount='bad')  # E: incompatible_argument
            Decorated(amount=1, excluded=2)  # E: incompatible_call
            assert_type(d.value, int)
            d.value = 2  # E: incompatible_assignment
            Derived('text')
            Derived('text', 2)
            Derived()  # E: incompatible_call
            Derived(1)  # E: incompatible_argument
            assert_type(b.value, str)
            MetaRecord(b'bytes')
            MetaRecord()  # E: incompatible_call
            MetaRecord('text')  # E: incompatible_argument
            assert_type(m.value, bytes)
        @record
        class Conflict(Base):  # E: multiple_dataclass_transform
            value: int
    ''')
